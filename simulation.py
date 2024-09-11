import redis.asyncio as aioredis
import asyncio
import os
from logger_setup import app_logger
from position_manager import PositionManager
from websocket_manager import WebSocketManager
from market_data_processor import MarketDataProcessor
from order_execution_engine import OrderExecutionEngine
from config import Config
from utils import login
from influxdb_manager import InfluxDBManager
from margin_calculator import MarginCalculator
from straddle import Straddle
from dotenv import load_dotenv
from datetime import datetime, timedelta

class SimulationManager:
    def __init__(self, config, api):
        self.config = config
        influxdb_config = self.config.get_influxdb_config()
        self.api = api
        self.websocket_manager = WebSocketManager(api, config)
        self.market_data_processor = MarketDataProcessor(config)
        self.redis = None
        self.influxdb_manager = InfluxDBManager(
            url=influxdb_config.get('url'),
            token=influxdb_config.get('token'),
            org=influxdb_config.get('org'),
            bucket=influxdb_config.get('bucket'),
            send_data_to_influxdb=config.get_rule('send_data_to_influxdb')
        )
        self.position_manager = PositionManager(self.market_data_processor, self.influxdb_manager)
        self.order_execution_engine = OrderExecutionEngine(self.market_data_processor, self.position_manager, config)
        self.margin_calculator = MarginCalculator(api, config.get_config('user'))
        self.strategy = Straddle(config, api, self.websocket_manager, self.market_data_processor, 
                                 self.position_manager, self.order_execution_engine, self.margin_calculator)

    async def setup(self):
        await self.websocket_manager.connect()
        await self.market_data_processor.connect()
        await self.order_execution_engine.connect()
        redis_config = self.config.get_redis_config()
        self.redis = await self.connect_to_redis(redis_config)

    async def connect_to_redis(self, redis_config):
        retries = 1
        for i in range(retries):
            try:
                redis = await aioredis.from_url(f"redis://{redis_config.get('host')}:{redis_config.get('port')}")
                app_logger.info("Connected to Redis.")
                return redis
            except aioredis.ConnectionError as e:
                if i == retries - 1:
                    app_logger.error(f"Failed to connect to Redis after {retries} retries: {e}")
                    raise
                app_logger.warning(f"Failed to connect to Redis. Retrying in 2 seconds... ({i + 1}/{retries})")
                await asyncio.sleep(2)

    async def cleanup(self):
        self.influxdb_manager.close()
        await self.websocket_manager.close()
        await self.market_data_processor.close()
        await self.order_execution_engine.close()
        await self.redis.aclose()

    async def run(self):
        app_logger.info("Starting simulation.")
        await self.setup()

        while not self.websocket_manager.feed_opened:
            await asyncio.sleep(0.1)
        
        app_logger.info("WebSocket connected. Proceeding with simulation.")

        option_symbols, final_quantity, final_trade_margin, atm_strike = await self.strategy.setup()
        if not option_symbols or final_quantity <= 0:
            app_logger.error("Strategy setup failed. Aborting simulation.")
            await self.cleanup()
            return

        end_time = datetime.strptime(self.config.get_rule('end_time'), '%H:%M:%S').time()
        await self.strategy.execute(option_symbols, final_quantity, atm_strike, end_time)

        await self.cleanup()

async def main():
    load_dotenv()
    config_file = os.environ.get('CONFIG_FILE', '/app/creds/config.yaml')
    rules_file = os.environ.get('RULES_FILE', '/app/creds/tbs_rules.yaml')
    
    config = Config(config_file, rules_file)
    api = login(config)
    
    simulation = SimulationManager(config, api)
    
    # Get the start time from the rules file
    start_time = datetime.strptime(config.get_rule('start_time'), '%H:%M:%S').time()
    
    # Calculate the delay until the start time
    now = datetime.now().time()
    if now < start_time:
        delay = (datetime.combine(datetime.today(), start_time) - datetime.combine(datetime.today(), now)).total_seconds()
    else:
        delay = (datetime.combine(datetime.today() + timedelta(days=1), start_time) - datetime.combine(datetime.today(), now)).total_seconds()
    
    app_logger.info(f"Waiting for {delay} seconds until start time: {start_time}")
    await asyncio.sleep(delay)
    
    await simulation.run()

if __name__ == "__main__":
    asyncio.run(main())