import asyncio
import redis.asyncio as aioredis
import json
from app.logger_setup import app_logger

class MarketDataProcessor:
    def __init__(self, config):
        self.config = config
        self.redis = None
        self.pubsub = None
        self.token_symbol_map = {}

    async def connect(self):
        redis_config = self.config.get_redis_config()
        self.redis = await self.connect_redis(redis_config)
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe('market_data')
        asyncio.create_task(self.process_market_data())

    async def connect_redis(self, redis_config, max_retries=5, retry_delay=2):
        for attempt in range(max_retries):
            try:
                redis = await aioredis.from_url(f"redis://redis:{redis_config.get('port')}")
                return redis
            except Exception as e:
                app_logger.error(f"Failed to connect to Redis (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        raise ConnectionError("Failed to connect to Redis after multiple attempts")

    async def process_market_data(self):
        try:
            while True:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    data = json.loads(message['data'])
                    app_logger.debug(f"Received market data: {data}")  # Add this line
                    await self.update_market_data(data)
                await asyncio.sleep(0.01)  # Small delay to prevent busy waiting
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_logger.error(f"Error processing market data: {e}", exc_info=True)

    async def update_market_data(self, data):
        if 'lp' in data and 'tk' in data:
            token = data['tk']
            ltp = float(data['lp'])
            symbol = data.get('ts')

            if symbol:
                self.token_symbol_map[token] = symbol
                await self.redis.hset('token_symbol_map', token, symbol)

            symbol = self.token_symbol_map.get(token) or await self.redis.hget('token_symbol_map', token)
            symbol = symbol.decode('utf-8') if isinstance(symbol, bytes) else symbol

            if symbol:
                await self.redis.hset(f'market_data:{symbol}', 'ltp', ltp)

    async def get_ltp(self, symbol):
        ltp = await self.redis.hget(f'market_data:{symbol}', 'ltp')
        if ltp is None:
            app_logger.warning(f"LTP not found for symbol: {symbol}")
        else:
            app_logger.debug(f"LTP found for symbol: {symbol}, value: {ltp}")
        return float(ltp) if ltp else None

    async def get_ltp_with_retry(self, token, max_retries=5, retry_delay=1):
        for _ in range(max_retries):
            ltp = await self.get_ltp(token)
            if ltp is not None:
                return ltp
            app_logger.warning(f"LTP not available for {token}. Retrying...")
            await asyncio.sleep(retry_delay)
        app_logger.error(f"Failed to get LTP for {token} after {max_retries} retries.")
        return None

    async def close(self):
        if self.pubsub:
            await self.pubsub.unsubscribe('market_data')
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()