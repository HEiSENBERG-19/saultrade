import redis.asyncio as aioredis
import json
from logger_setup import app_logger

class OrderExecutionEngine:
    def __init__(self, market_data_processor, position_manager, config):
        self.config = config
        self.redis = None
        self.market_data_processor = market_data_processor
        self.position_manager = position_manager

    async def connect(self):
        redis_config = self.config.get_redis_config()
        self.redis = await aioredis.from_url(f"redis://{redis_config.get('host')}:{redis_config.get('port')}")

    async def place_order(self, order_details):
        order_id = await self.generate_order_id()
        order_details['order_id'] = order_id

        ltp = await self.market_data_processor.get_ltp(order_details['symbol'])
        if ltp is None:
            app_logger.error(f"Unable to get LTP for {order_details['symbol']}. Order not placed.")
            return None

        if order_details['order_type'] == 'MKT':
            order_details['price'] = ltp
        elif order_details['order_type'] == 'SL-M':
            order_details['trigger_price'] = order_details['trigger_price']

        await self.redis.set(f"order:{order_id}", json.dumps(order_details))

        await self.redis.publish('orders', json.dumps(order_details))
        
        price_info = f"@ {order_details['price']}" if 'price' in order_details else f"trigger @ {order_details['trigger_price']}"
        app_logger.info(f"Order placed: {order_details['symbol']} {order_details['direction']} {order_details['quantity']} {price_info}")
        
        return order_details

    async def generate_order_id(self):
        return await self.redis.incr('order_id_counter')

    def is_sl_triggered(self, order, ltp):
        if order['direction'] == 'B':
            return ltp >= order['trigger_price']
        else:
            return ltp <= order['trigger_price']

    async def execute_stop_loss(self, sl_order_id):
        sl_order = await self.redis.get(f"order:{sl_order_id}")
        if not sl_order:
            app_logger.error(f"Stop loss order {sl_order_id} not found")
            return False

        sl_order = json.loads(sl_order)
        
        ltp = await self.market_data_processor.get_ltp(sl_order['symbol'])
        if ltp is None:
            app_logger.error(f"Unable to get LTP for {sl_order['symbol']}. Stop loss not executed.")
            return False

        if self.is_sl_triggered(sl_order, ltp):
            await self.position_manager.update_position(sl_order['symbol'], ltp)
            
            await self.redis.delete(f"order:{sl_order_id}")
            return True

        return False   
    
    async def close(self):
        await self.redis.close()