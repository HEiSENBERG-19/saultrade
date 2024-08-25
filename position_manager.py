import asyncio
from logger_setup import app_logger, pnl_logger

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
        
        self.influxdb_manager.write_data(
            measurement="positions",
            fields={"quantity": quantity, "price": price},
            tags={"symbol": symbol, "action": "add"}
        )

    async def update_position(self, symbol, new_price):
        if symbol in self.positions:
            old_price = self.positions[symbol]['current_price']
            quantity = self.positions[symbol]['quantity']
            entry_price = self.positions[symbol]['entry_price']
            self.positions[symbol]['current_price'] = new_price
            self.total_current_value += quantity * (new_price - old_price)
            
            position_pnl = (entry_price - new_price) * quantity
            await self.calculate_pnl()
            
            self.influxdb_manager.write_data(
                measurement="positions",
                fields={"price": new_price, "pnl": position_pnl},
                tags={"symbol": symbol}
            )

    async def calculate_pnl(self):
            total_pnl = self.total_entry_value - self.total_current_value
            roi = 0
            if self.total_entry_value != 0:
                if self.trade_margin != 0:
                    roi = (total_pnl / self.trade_margin) * 100
                self.influxdb_manager.write_data(
                    measurement="pnl",
                    fields={
                        "total_pnl": total_pnl, 
                        "roi": roi,
                    }
                )
            return total_pnl, roi

    async def get_total_pnl(self):
        return await self.calculate_pnl()

    async def check_stop_loss(self, symbol, stop_loss_price):
        if symbol in self.positions:
            current_price = self.positions[symbol]['current_price']
            if current_price >= stop_loss_price:
                return True
        return False

    async def get_all_positions(self):
        return self.positions