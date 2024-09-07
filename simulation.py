import redis.asyncio as aioredis
import asyncio
import os
import subprocess
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

class SimulationManager:
    def __init__(self, config, api):
        self.config = config
        influxdb_config = self.config.get_influxdb_config()
        self.api = api
        self.websocket_manager = WebSocketManager(api)
        self.market_data_processor = MarketDataProcessor()
        self.redis = None
        self.influxdb_manager = InfluxDBManager(
            url=influxdb_config.get('url'),
            token=influxdb_config.get('token'),
            org=influxdb_config.get('org'),
            bucket=influxdb_config.get('bucket')
        )
        self.position_manager = PositionManager(self.market_data_processor, self.influxdb_manager)
        self.order_execution_engine = OrderExecutionEngine(self.market_data_processor, self.position_manager)
        self.margin_calculator = MarginCalculator(api, config.get_config('user'))
        self.strategy = Straddle(config, api, self.websocket_manager, self.market_data_processor, 
                                 self.position_manager, self.order_execution_engine, self.margin_calculator)

    async def setup(self):
        await self.websocket_manager.connect()
        await self.market_data_processor.connect()
        await self.order_execution_engine.connect()
        self.redis = await aioredis.from_url("redis://localhost")

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

        await self.strategy.execute(option_symbols, final_quantity, atm_strike)

        await self.cleanup()

async def start_redis_server(redis_dir):
    try:
        os.chdir(redis_dir)
        process = subprocess.Popen(['redis-server'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("Redis server started.")
    except Exception as e:
        print(f"Failed to start Redis server: {e}")

async def start_docker_compose():
    try:
        process = subprocess.Popen(['docker-compose', 'start'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("Docker containers started.")
    except Exception as e:
        print(f"Failed to start Docker containers: {e}")

async def main():
    redis_dir = r'redis'
    
    await asyncio.gather(
        start_redis_server(redis_dir),
        start_docker_compose()
    )

    load_dotenv()
    config_file = os.environ.get('CONFIG_FILE', '/home/heisenberg/saultrade/creds/config.yaml')
    rules_file = os.environ.get('RULES_FILE', '/home/heisenberg/saultrade/creds/tbs_rules.yaml')
    
    config = Config(config_file, rules_file)
    api = login(config)
    
    simulation = SimulationManager(config, api)
    await simulation.run()

if __name__ == "__main__":
    asyncio.run(main())
