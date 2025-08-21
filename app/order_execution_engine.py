import redis.asyncio as aioredis
import json
from app.logger_setup import app_logger, pos_logger


class OrderExecutionEngine:
    def __init__(self, market_data_processor, position_manager, config):
        self.config = config
        self.redis = None
        self.market_data_processor = market_data_processor
        self.position_manager = position_manager

    async def connect(self):
        redis_config = self.config.get_redis_config()
        self.redis = await aioredis.from_url(
            f"redis://{redis_config.get('host')}:{redis_config.get('port')}"
        )

    async def place_order(self, order_details):
        order_id = await self.generate_order_id()
        order_details["order_id"] = order_id

        # For MKT orders, we need the current price to simulate the fill
        if order_details["order_type"] == "MKT":
            ltp = await self.market_data_processor.get_ltp(order_details["symbol"])
            if ltp is None:
                app_logger.error(
                    f"Unable to get LTP for {order_details['symbol']}. MKT order not placed."
                )
                return None
            order_details["price"] = ltp

        # For SL orders, we just store the trigger price
        elif order_details["order_type"] == "SL-M":
            # Price is not known until triggered, so we don't set it here
            pass

        await self.redis.set(f"order:{order_id}", json.dumps(order_details))
        await self.redis.publish("orders", json.dumps(order_details))

        price_info = (
            f"@ {order_details['price']}"
            if "price" in order_details
            else f"trigger @ {order_details['trigger_price']}"
        )
        app_logger.info(
            f"Order placed: {order_details['symbol']} {order_details['direction']} "
            f"{order_details['quantity']} {price_info}"
        )

        return order_details

    async def confirm_execution(
        self, symbol, quantity, price, direction, order_id_to_remove=None
    ):
        if direction == "S" or direction == "B":  # Initial trade or closing trade
            await self.position_manager.add_position(symbol, quantity, price, direction)
            pos_logger.info(f"Position opened for {symbol} at {price}")

        elif direction == "CLOSE":  # Closing a trade
            await self.position_manager.close_position(symbol, price, quantity)
            pos_logger.info(f"Position closed for {symbol} at {price}")

        if order_id_to_remove:
            await self.redis.delete(f"order:{order_id_to_remove}")

        return True

    async def generate_order_id(self):
        return await self.redis.incr("order_id_counter")

    async def close(self):
        await self.redis.close()