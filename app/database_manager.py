import redis.asyncio as aioredis
from influxdb_client import InfluxDBClient
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, config):
        self.config = config
        self.redis: Optional[aioredis.Redis] = None
        self.influxdb: Optional[InfluxDBClient] = None

    async def connect_redis(self) -> aioredis.Redis:
        try:
            redis_config = self.config.get_redis_config()
            self.redis = await aioredis.from_url(
                f"redis://{redis_config.get('host')}:{redis_config.get('port')}"
            )
            return self.redis
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
            raise

    def connect_influxdb(self) -> InfluxDBClient:
        try:
            influxdb_config = self.config.get_influxdb_config()
            self.influxdb = InfluxDBClient(
                url=influxdb_config.get('url'),
                token=influxdb_config.get('token'),
                org=influxdb_config.get('org')
            )
            return self.influxdb
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}", exc_info=True)
            raise

    async def close(self):
        try:
            if self.redis:
                await self.redis.aclose()
            if self.influxdb:
                self.influxdb.close()
        except Exception as e:
            logger.error(f"Error while closing database connections: {e}", exc_info=True)