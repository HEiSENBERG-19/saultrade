class PositionManager:
    def __init__(self, market_data_processor, influxdb_manager):
        self.positions = {}
        self.market_data_processor = market_data_processor
        self.total_entry_value = 0
        self.total_current_value = 0
        self.influxdb_manager = influxdb_manager
        self.trade_margin = 0
    
    def set_trade_margin(self, margin):
        self.trade_margin = margin

    async def add_position(self, symbol, quantity, price):
        self.positions[symbol] = {
            'quantity': quantity,
            'entry_price': price,
            'current_price': price
        }
        self.total_entry_value += quantity * price
        self.total_current_value += quantity * price
        
        self._write_position_data(symbol, quantity, price, "add")
        await self._write_pnl_data()

    async def update_position(self, symbol, new_price):
        if symbol in self.positions:
            old_price = self.positions[symbol]['current_price']
            quantity = self.positions[symbol]['quantity']
            entry_price = self.positions[symbol]['entry_price']
            self.positions[symbol]['current_price'] = new_price
            self.total_current_value += quantity * (new_price - old_price)
            
            position_pnl = (new_price - entry_price) * quantity
            self._write_position_data(symbol, quantity, new_price, "update", position_pnl)
            await self._write_pnl_data()

    async def calculate_pnl(self):
        total_pnl = self.total_entry_value - self.total_current_value
        roi = 0
        if self.total_entry_value != 0 and self.trade_margin != 0:
            roi = (total_pnl / self.trade_margin) * 100
        return total_pnl, roi

    async def get_total_pnl(self):
        return await self.calculate_pnl()

    async def check_stop_loss(self, symbol, stop_loss_price):
        if symbol in self.positions:
            current_price = self.positions[symbol]['current_price']
            return current_price >= stop_loss_price
        return False

    async def get_all_positions(self):
        return self.positions

    def _write_position_data(self, symbol, quantity, price, action, pnl=None):
        fields = {"quantity": quantity, "price": price}
        if pnl is not None:
            fields["pnl"] = pnl
        
        self.influxdb_manager.write_data(
            measurement="positions",
            fields=fields,
            tags={"symbol": symbol, "action": action}
        )

    async def _write_pnl_data(self):
        total_pnl, roi = await self.calculate_pnl()
        self.influxdb_manager.write_data(
            measurement="pnl",
            fields={
                "total_pnl": total_pnl, 
                "roi": roi,
                "total_entry_value": self.total_entry_value,
                "total_current_value": self.total_current_value
            }
        )

    async def _write_option_prices(self):
        for symbol, data in self.positions.items():
            self.influxdb_manager.write_data(
                measurement="option_prices",
                fields={"price": data['current_price']},
                tags={"symbol": symbol}
            )