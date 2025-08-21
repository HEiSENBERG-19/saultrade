# app/market_data_processor.py
import asyncio
import redis.asyncio as aioredis
import json
from typing import Optional
from app.logger_setup import app_logger

class MarketDataProcessor:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.pubsub = None
        self.token_symbol_map = {}
        self._processing_task = None

    async def connect(self):
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe('market_data')
        self._processing_task = asyncio.create_task(self.process_market_data())

    async def process_market_data(self):
        try:
            while True:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    try:
                        data = json.loads(message['data'])
                        await self.update_market_data(data)
                    except json.JSONDecodeError:
                        app_logger.warning(f"Received non-JSON market data: {message['data']}")
                    except Exception as e:
                        app_logger.error(f"Error handling market data message: {e}", exc_info=True)
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            app_logger.info("Market data processing task cancelled.")
        except Exception as e:
            app_logger.error(f"Error in process_market_data loop: {e}", exc_info=True)

    async def update_market_data(self, data: dict):
        if 'lp' in data and 'tk' in data:
            token = data['tk']
            ltp = float(data['lp'])
            symbol = data.get('ts')

            if symbol and self.token_symbol_map.get(token) != symbol:
                self.token_symbol_map[token] = symbol
                await self.redis.hset('token_symbol_map', token, symbol)

            if token not in self.token_symbol_map:
                redis_symbol = await self.redis.hget('token_symbol_map', token)
                if redis_symbol:
                    self.token_symbol_map[token] = redis_symbol.decode('utf-8')
            
            final_symbol = self.token_symbol_map.get(token)
            if final_symbol:
                await self.redis.hset(f'market_data:{final_symbol}', 'ltp', ltp)

    async def get_ltp(self, symbol: str) -> Optional[float]:
        ltp = await self.redis.hget(f'market_data:{symbol}', 'ltp')
        if ltp is None:
            app_logger.warning(f"LTP not found for symbol: {symbol}")
            return None
        return float(ltp)

    async def get_ltp_with_retry(self, symbol: str, max_retries: int = 5, retry_delay: float = 1.0) -> Optional[float]:
        for attempt in range(max_retries):
            ltp = await self.get_ltp(symbol)
            if ltp is not None:
                return ltp
            app_logger.warning(f"LTP not available for {symbol}. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
            await asyncio.sleep(retry_delay)
        app_logger.error(f"Failed to get LTP for {symbol} after {max_retries} retries.")
        return None

    async def close(self):
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        
        if self.pubsub:
            await self.pubsub.unsubscribe('market_data')
            await self.pubsub.close()
            app_logger.info("Unsubscribed from market_data and closed pubsub.")