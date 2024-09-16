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
        self.total_premium = 0

    def set_trade_margin(self, margin):
        self.trade_margin = margin

    async def add_position(self, symbol, quantity, price):
        self.positions[symbol] = {
            'quantity': quantity,
            'entry_price': price,
            'current_price': price
        }

        await self._update_influx()

    async def _update_influx(self):
        points = []

        # 1. List of positions
        for symbol, data in self.positions.items():
            points.append({
                "measurement": "positions",
                "fields": {
                    "symbol": symbol,
                    "quantity": data['quantity'],
                    "entry_price": data['entry_price'],
                    "current_price": data['current_price']
                }
            })

        # 2. ROI and 3. Total PNL
        total_pnl = self.total_entry_value - self.total_current_value
        roi = (total_pnl / self.trade_margin) * 100 if self.trade_margin != 0 else 0
        points.append({
            "measurement": "performance",
            "fields": {
                "total_pnl": total_pnl,
                "roi": roi
            }
        })

        # 3. Pricing of individual options
        for symbol, data in self.positions.items():
            points.append({
                "measurement": "option_prices",
                "fields": {
                    "symbol": symbol,
                    "price": data['current_price']
                }
            })

        self.influxdb_manager.write_points(points)

    async def calculate_pnl(self):
        total_pnl = self.total_entry_value - self.total_current_value
        roi = (total_pnl / self.trade_margin) * 100 if self.trade_margin != 0 else 0
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