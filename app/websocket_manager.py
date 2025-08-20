import asyncio
import redis.asyncio as aioredis
import json
from app.logger_setup import app_logger, ws_logger
from queue import Queue
from threading import Thread

class WebSocketManager:
    def __init__(self, api, config):
        self.api = api
        self.config = config
        self.redis = None
        self.feed_opened = False
        self.message_queue = Queue()
        self.processing_task = None

    async def connect(self):
        redis_config = self.config.get_redis_config()
        self.redis = await aioredis.from_url(f"redis://{redis_config.get('host')}:{redis_config.get('port')}")
        await self.start_websocket()
        self.processing_task = asyncio.create_task(self.process_queue())

    async def start_websocket(self):
        def run_websocket():
            self.api.start_websocket(
                order_update_callback=self.sync_event_handler_order_update,
                subscribe_callback=self.sync_event_handler_feed_update,
                socket_open_callback=self.open_callback
            )

        Thread(target=run_websocket, daemon=True).start()

    def sync_event_handler_feed_update(self, tick_data):
        self.message_queue.put(('feed_update', tick_data))

    def sync_event_handler_order_update(self, order):
        self.message_queue.put(('order_update', order))

    async def process_queue(self):
        while True:
            while not self.message_queue.empty():
                message_type, data = self.message_queue.get()
                if message_type == 'feed_update':
                    await self.event_handler_feed_update(data)
                elif message_type == 'order_update':
                    await self.event_handler_order_update(data)
            await asyncio.sleep(0.1)  # Small delay to prevent busy waiting

    async def event_handler_feed_update(self, tick_data):
        # ws_logger.info(f"feed update: {tick_data}")
        await self.redis.publish('market_data', json.dumps(tick_data))

    async def event_handler_order_update(self, order):
        ws_logger.info(f"order update: {order}")
        await self.redis.publish('order_updates', json.dumps(order))

    def open_callback(self):
        self.feed_opened = True
        ws_logger.info("WebSocket feed opened")

    async def subscribe_symbol(self, exchange, token, trading_symbol):
        try:
            self.api.subscribe(f'{exchange}|{token}')
            ws_logger.info(f"Subscribed to symbol: {trading_symbol}")
        except Exception as e:
            app_logger.error(f"Error subscribing to {exchange}|{token}: {e}")

    async def unsubscribe_symbol(self, exchange, token, trading_symbol):
        try:
            self.api.unsubscribe(f'{exchange}|{token}')
            ws_logger.info(f"Unsubscribed from symbol: {trading_symbol}")
        except Exception as e:
            app_logger.error(f"Error unsubscribing from {exchange}|{token}: {e}")

    async def close(self):
        if self.processing_task:
            self.processing_task.cancel()
        await self.redis.close()