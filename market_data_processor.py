import asyncio
import redis.asyncio as aioredis
import json
from logger_setup import app_logger

class MarketDataProcessor:
    def __init__(self, config):
        self.config = config
        self.redis = None
        self.token_symbol_map = {}

    async def connect(self):
        redis_config = self.config.get_redis_config()
        self.redis = await aioredis.from_url(f"redis://{redis_config.get('host')}:{redis_config.get('port')}")
        asyncio.create_task(self.process_market_data())

    async def process_market_data(self):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe('market_data')
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True)
            if message:
                data = json.loads(message['data'])
                await self.update_market_data(data)

    async def update_market_data(self, data):
        if 'lp' in data and 'tk' in data:
            token = data['tk']
            ltp = float(data['lp'])  
            if 'ts' in data:
                symbol = data['ts']
                self.token_symbol_map[token] = symbol
                await self.redis.hset(f'token_symbol_map', token, symbol)
            symbol = self.token_symbol_map.get(token) or await self.redis.hget('token_symbol_map', token)
            if symbol:
                self.token_symbol_map[token] = symbol.decode('utf-8') if isinstance(symbol, bytes) else symbol
            display_id = symbol if symbol else token
            await self.redis.hset(f'market_data:{symbol}', 'ltp', ltp)

    async def get_ltp(self, symbol):
        ltp = await self.redis.hget(f'market_data:{symbol}', 'ltp')
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
        await self.redis.close()