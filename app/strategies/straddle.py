import asyncio
from datetime import datetime
from app.logger_setup import app_logger, pos_logger
from app.utils import get_atm_strike, get_option_symbols, adjust_quantity_for_lot_size

class Straddle:
    def __init__(self, config, api, websocket_manager, market_data_processor, position_manager, order_execution_engine, margin_calculator):
        self.config = config
        self.api = api
        self.websocket_manager = websocket_manager
        self.market_data_processor = market_data_processor
        self.position_manager = position_manager
        self.order_execution_engine = order_execution_engine
        self.margin_calculator = margin_calculator
        self.stop_loss_percentage = self.config.get_rule('stop_loss_percentage') / 100

    async def setup(self):
        option_symbols, atm_strike = await self._get_option_symbols()
        if not option_symbols:
            return None, None, 0, None

        final_quantity = await self._calculate_final_quantity(option_symbols)
        if final_quantity <= 0:
            return None, None, 0, None

        final_margin, final_trade_margin = await self._calculate_margin(option_symbols, final_quantity)
        
        await self.subscribe_to_symbols(option_symbols)
        
        await asyncio.sleep(1)

        return option_symbols, final_quantity, final_trade_margin, atm_strike

    async def execute(self, option_symbols, final_quantity, atm_strike, end_time):
        initial_order_details = await self.place_initial_orders(option_symbols, final_quantity)
        stop_loss_orders = await self.place_stop_loss_orders(initial_order_details, final_quantity)

        await self.monitor_positions_and_stop_loss(stop_loss_orders, option_symbols, final_quantity, end_time)

        # PnL calculation is now handled by PositionManager, we can query it if needed
        # final_pnl, roi = await self.position_manager.calculate_pnl()
        # app_logger.info(f"Final P&L: Rs{final_pnl:.2f}")
        # app_logger.info(f"Final ROI: {roi:.2f}%")

        await self.unsubscribe_from_symbols(option_symbols)

    async def _get_option_symbols(self):
        try:
            atm_strike = await get_atm_strike(
                self.config.get_rule('tsymbol'), 
                lambda e, t: self.api.get_quotes(e, t)
            )
            if not atm_strike:
                app_logger.error("Failed to get ATM strike. Aborting simulation.")
                return None, None
            
            strikes = {
                'sce': (atm_strike + self.config.get_rule('sotm_points') + self.config.get_rule('bias_points'), 'CE'),
                'spe': (atm_strike - self.config.get_rule('sotm_points') + self.config.get_rule('bias_points'), 'PE'),
            }
            option_symbols = await get_option_symbols(self.config.get_rule('tsymbol'), strikes)
            if not option_symbols:
                app_logger.error("Failed to get option symbols. Aborting simulation.")
                return None, None
            return option_symbols, atm_strike
        except Exception as e:
            app_logger.error(f"Error getting option symbols: {e}")
            return None, None

    async def subscribe_to_symbols(self, option_symbols):
        for symbol in option_symbols.values():
            await self.websocket_manager.subscribe_symbol(symbol['Exchange'], symbol['Token'], symbol['TradingSymbol'])

    async def unsubscribe_from_symbols(self, option_symbols):
        for symbol in option_symbols.values():
            await self.websocket_manager.unsubscribe_symbol(symbol['Exchange'], symbol['Token'], symbol['TradingSymbol'])

    async def _calculate_final_quantity(self, option_symbols):
        final_quantity = int(adjust_quantity_for_lot_size(self.config.get_rule('quantity'), option_symbols['sce']['LotSize']))

        if final_quantity <= 0:
            app_logger.error("Final quantity <= zero. Aborting simulation.")
            return 0

        return final_quantity
    
    async def _calculate_margin(self, option_symbols, final_quantity):
        required_margin, final_trade_margin = await self.margin_calculator.calculate_margin(option_symbols, final_quantity)
        self.position_manager.set_trade_margin(final_trade_margin)
        return required_margin, final_trade_margin   
   
    async def place_initial_orders(self, option_symbols, final_quantity):
        initial_order_details = []
        for symbol in option_symbols.values():
            order = {
                'symbol': symbol['TradingSymbol'],
                'direction': 'S',
                'quantity': final_quantity,
                'order_type': 'MKT'
            }
            order_response = await self.order_execution_engine.place_order(order)
            if order_response:
                order_id = order_response['order_id']
                executed_price = order_response['price']
                
                # Tell the engine to confirm the execution, which updates the position manager
                await self.order_execution_engine.confirm_execution(
                    symbol=symbol['TradingSymbol'],
                    quantity=final_quantity,
                    price=executed_price,
                    direction=order['direction']
                )

                initial_order_details.append({
                    'symbol': symbol['TradingSymbol'],
                    'order_id': order_id,
                    'executed_price': executed_price
                })
        return initial_order_details

    async def place_stop_loss_orders(self, initial_order_details, final_quantity):
        stop_loss_orders = []
        for order_detail in initial_order_details:
            sl_price = round(order_detail['executed_price'] * (1 + self.stop_loss_percentage), 2)
            
            sl_order = {
                'symbol': order_detail['symbol'],
                'direction': 'B',
                'quantity': final_quantity,
                'order_type': 'SL-M',
                'trigger_price': sl_price,
                'parent_order_id': order_detail['order_id']
            }
            sl_order_response = await self.order_execution_engine.place_order(sl_order)
            if sl_order_response:
                stop_loss_orders.append({
                    'symbol': order_detail['symbol'],
                    'sl_order_id': sl_order_response['order_id'],
                    'sl_price': sl_price
                })
        return stop_loss_orders

    async def monitor_positions_and_stop_loss(self, stop_loss_orders, option_symbols, final_quantity, end_time):
        while True:
            current_time = datetime.now().time()
            if current_time >= end_time:
                app_logger.info("End time reached. Closing all positions.")
                await self.close_all_positions(option_symbols, final_quantity)
                return

            positions = await self.position_manager.get_all_positions()
            
            if not positions:
                app_logger.info("All positions closed. Exiting simulation.")
                return

            positions_copy = dict(positions)

            for symbol, position in positions_copy.items():
                if symbol not in positions:
                    continue

                current_price = await self.market_data_processor.get_ltp(symbol)
                if current_price:
                    await self.position_manager.update_position_price(symbol, current_price)

                    for sl_order in stop_loss_orders[:]:
                        if sl_order['symbol'] == symbol:
                            # Note: Position quantity is now negative for shorts
                            if (position['quantity'] < 0 and current_price >= sl_order['sl_price']):
                                app_logger.info(f"Stop loss triggered for {symbol} at {current_price}")

                                # Tell the engine to confirm the close execution
                                await self.order_execution_engine.confirm_execution(
                                    symbol=symbol,
                                    quantity=abs(position['quantity']),
                                    price=current_price,
                                    direction='CLOSE',
                                    order_id_to_remove=sl_order['sl_order_id']
                                )

                                stop_loss_orders.remove(sl_order)
                                break # Exit inner loop for this symbol as its position is closed

            await asyncio.sleep(1)

    async def close_all_positions(self, option_symbols, final_quantity):
        # Make a copy of positions to iterate over, as the original dict will be modified
        open_positions = dict(self.position_manager.positions)
        for trading_symbol, position_details in open_positions.items():
            # Find the corresponding symbol details from option_symbols
            symbol_info = next((s for s in option_symbols.values() if s['TradingSymbol'] == trading_symbol), None)
            if symbol_info:
                order = {
                    'symbol': trading_symbol,
                    'direction': 'B', # Always buying to close a short straddle
                    'quantity': abs(position_details['quantity']),
                    'order_type': 'MKT'
                }
                order_response = await self.order_execution_engine.place_order(order)
                if order_response:
                    executed_price = order_response['price']
                    
                    # Tell the engine to confirm the close execution
                    await self.order_execution_engine.confirm_execution(
                        symbol=trading_symbol,
                        quantity=abs(position_details['quantity']),
                        price=executed_price,
                        direction='CLOSE'
                    )