# app/order_execution_engine.py
import redis.asyncio as aioredis
import json
from typing import Optional
from app.logger_setup import app_logger, pos_logger
from .market_data_processor import MarketDataProcessor
from .position_manager import PositionManager

class OrderExecutionEngine:
    def __init__(
        self,
        market_data_processor: MarketDataProcessor,
        position_manager: PositionManager,
        redis_client: aioredis.Redis,
    ):
        self.market_data_processor = market_data_processor
        self.position_manager = position_manager
        self.redis = redis_client
    
    async def place_order(self, order_details: dict) -> Optional[dict]:
        order_id = await self.generate_order_id()
        order_details["order_id"] = order_id

        if order_details.get("order_type") == "MKT":
            ltp = await self.market_data_processor.get_ltp(order_details["symbol"])
            if ltp is None:
                app_logger.error(
                    f"Unable to get LTP for {order_details['symbol']}. MKT order cannot be placed."
                )
                return None
            order_details["price"] = ltp
        
        await self.redis.set(f"order:{order_id}", json.dumps(order_details))
        await self.redis.publish("orders", json.dumps(order_details))

        price_info = (
            f"at market price ~{order_details.get('price')}"
            if "price" in order_details
            else f"with trigger price {order_details.get('trigger_price')}"
        )
        app_logger.info(
            f"Simulated order placed: ID {order_id} for {order_details['symbol']} "
            f"({order_details['direction']} {order_details['quantity']}) {price_info}"
        )

        return order_details

    async def confirm_execution(
        self, symbol: str, quantity: int, price: float, direction: str, order_id_to_remove: int = None
    ):
        if direction in ("S", "B"):
            await self.position_manager.add_position(symbol, quantity, price, direction)
            pos_logger.info(f"Position opened/updated for {symbol} at {price}")
        elif direction == "CLOSE":
            await self.position_manager.close_position(symbol, price, quantity)
            pos_logger.info(f"Position closed for {symbol} at {price}")

        if order_id_to_remove:
            await self.redis.delete(f"order:{order_id_to_remove}")

        return True

    async def generate_order_id(self) -> int:
        return await self.redis.incr("order_id_counter")