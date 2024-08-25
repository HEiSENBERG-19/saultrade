import logging, asyncio
from NorenRestApiPy.NorenApi import position
from utils import get_account_limits  
from logger_setup import app_logger

class MarginCalculator:
    def __init__(self, api, account_id):
        self.api = api
        self.account_id = account_id

    async def calculate_margin(self, option_symbols, adjusted_quantity):
        try:
            position_list = self._create_position_list(option_symbols, adjusted_quantity)
            margin_result = await self._calculate_span(position_list)
            
            if margin_result and 'stat' in margin_result and margin_result['stat'] == 'Ok':
                span = float(margin_result.get('span', 0))
                expo = float(margin_result.get('expo', 0))
                span_trade = float(margin_result.get('span_trade', 0))
                expo_trade = float(margin_result.get('expo_trade', 0))
                
                margin = span + expo
                trade_margin = span_trade + expo_trade
                
                final_margin = round(margin * 1.009, 2)
                final_trade_margin = round(trade_margin * 1.009, 2)
                app_logger.info(f"Required margin: {final_trade_margin}")
                return final_margin, final_trade_margin
            else:
                app_logger.error(f"Error in margin calculation: {margin_result}")
                return None
        except Exception as e:
            app_logger.error(f"Error in calculate_margin: {e}", exc_info=True)
            return None

    def _create_position_list(self, option_symbols, adjusted_quantity):
        position_list = []
        for key, symbol_data in option_symbols.items():
            pos = position()
            pos.prd = 'I'  # Assuming NRML product type, change if needed
            pos.exch = symbol_data['Exchange']
            pos.instname = symbol_data['Instrument']
            pos.symname = symbol_data['Symbol']
            pos.exd = symbol_data['Expiry'].strftime('%d-%b-%Y').upper()
            pos.optt = symbol_data['OptionType']
            pos.strprc = str(symbol_data['StrikePrice'])
            pos.buyqty = '0'
            pos.sellqty = str(adjusted_quantity)
            pos.netqty = ''
            position_list.append(pos)
        return position_list

    async def _calculate_span(self, position_list):
        try:
            return await asyncio.to_thread(self.api.span_calculator, self.account_id, position_list)
        except Exception as e:
            app_logger.error(f"Error in _calculate_span: {e}", exc_info=True)
            return None

    async def get_available_margin(self) -> float:
        """Fetch and return the available margin for the account."""
        account_limits = await get_account_limits(self.api)
        if not account_limits:
            app_logger.warning("Failed to fetch account limits.")
            return 0
        return float(account_limits.get('cash', 0))

    async def calculate_max_quantity(self, option_symbols, lot_size: int):
        """Calculate the maximum quantity that can be traded based on available margin."""
        available_margin = await self.get_available_margin()
        app_logger.info(f"Available margin: {available_margin}")

        one_lot_margin = await self.calculate_margin(option_symbols, lot_size)
        if one_lot_margin is None:
            app_logger.warning("Failed to calculate margin for one lot.")
            return 0

        max_lots = int(available_margin / one_lot_margin[1])  # Using final_trade_margin
        app_logger.info(f"Maximum lots that can be traded: {max_lots}")

        return max_lots * lot_size