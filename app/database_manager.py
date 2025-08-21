import redis.asyncio as aioredis
from influxdb_client import InfluxDBClient
from typing import Optional
from app.config import Config
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, config: Config):
        self.config = config
        self.redis: Optional[aioredis.Redis] = None
        self.influxdb: Optional[InfluxDBClient] = None

    async def connect_redis(self) -> aioredis.Redis:
        if self.redis and await self.redis.ping():
            logger.info("Reusing existing Redis connection.")
            return self.redis
        try:
            redis_config = self.config.get_redis_config()
            self.redis = await aioredis.from_url(
                f"redis://{redis_config.get('host')}:{redis_config.get('port')}"
            )
            logger.info("Connected to Redis.")
            return self.redis
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
            raise

    def connect_influxdb(self) -> InfluxDBClient:
        if self.influxdb:
            return self.influxdb
        try:
            influxdb_config = self.config.get_influxdb_config()
            self.influxdb = InfluxDBClient(
                url=influxdb_config.get('url'),
                token=influxdb_config.get('token'),
                org=influxdb_config.get('org')
            )
            logger.info("Connected to InfluxDB.")
            return self.influxdb
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}", exc_info=True)
            raise

    async def close(self):
        try:
            if self.redis:
                await self.redis.close()
                logger.info("Redis connection closed.")
            if self.influxdb:
                self.influxdb.close()
                logger.info("InfluxDB connection closed.")
        except Exception as e:
            logger.error(f"Error while closing database connections: {e}", exc_info=True)