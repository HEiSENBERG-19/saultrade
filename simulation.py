import redis.asyncio as aioredis
import os
import asyncio
from app.logger_setup import app_logger
from app.position_manager import PositionManager
from app.websocket_manager import WebSocketManager
from app.market_data_processor import MarketDataProcessor
from app.order_execution_engine import OrderExecutionEngine
from app.config import Config
from app.utils import login
from app.influxdb_manager import InfluxDBManager
from app.margin_calculator import MarginCalculator
from app.strategies.straddle import Straddle
from app.database_manager import DatabaseManager
from datetime import datetime, timedelta

class SimulationManager:
    def __init__(self, config: Config, api):
        self.config = config
        self.api = api
        self.db_manager = DatabaseManager(config)
        influxdb_config = self.config.get_influxdb_config()
        self.influxdb_manager = InfluxDBManager(
            url=influxdb_config.get('url'),
            token=influxdb_config.get('token'),
            org=influxdb_config.get('org'),
            bucket=influxdb_config.get('bucket'),
            send_data_to_influxdb=config.get_rule('send_data_to_influxdb')
        )
        self.redis: aioredis.Redis = None
        self.market_data_processor: MarketDataProcessor = None
        self.position_manager: PositionManager = None
        self.order_execution_engine: OrderExecutionEngine = None
        self.websocket_manager: WebSocketManager = None
        self.margin_calculator: MarginCalculator = None
        self.strategy: Straddle = None

    async def setup(self):
        app_logger.info("Setting up simulation components...")
        self.redis = await self.db_manager.connect_redis()
        self.market_data_processor = MarketDataProcessor(self.redis)
        self.position_manager = PositionManager(self.market_data_processor, self.influxdb_manager)
        self.order_execution_engine = OrderExecutionEngine(self.market_data_processor, self.position_manager, self.redis)
        self.websocket_manager = WebSocketManager(self.api, self.redis)
        self.margin_calculator = MarginCalculator(self.api, self.config.get_user_credentials())
        self.strategy = Straddle(
            self.config, self.api, self.websocket_manager, self.market_data_processor,
            self.position_manager, self.order_execution_engine, self.margin_calculator
        )
        await self.market_data_processor.connect()
        await self.websocket_manager.connect()

    async def cleanup(self):
        if self.websocket_manager:
            await self.websocket_manager.close()
        if self.market_data_processor:
            await self.market_data_processor.close()
        if self.influxdb_manager:
            self.influxdb_manager.close()
        if self.db_manager:
            await self.db_manager.close()

    async def run(self):
        app_logger.info("Starting simulation.")
        try:
            await self.setup()

            while not self.websocket_manager.feed_opened:
                app_logger.debug("Waiting for WebSocket feed to open...")
                await asyncio.sleep(0.1)
            
            app_logger.info("WebSocket connected. Proceeding with simulation.")

            option_symbols, final_quantity, final_trade_margin, atm_strike = await self.strategy.setup()
            if not option_symbols or final_quantity <= 0:
                app_logger.error("Strategy setup failed. Aborting simulation.")
                return

            end_time = datetime.strptime(self.config.get_rule('end_time'), '%H:%M:%S').time()
            await self.strategy.execute(option_symbols, final_quantity, atm_strike, end_time)

        except Exception as e:
            app_logger.error(f"An error occurred during the simulation run: {e}", exc_info=True)
        finally:
            await self.cleanup()

async def main():
    rules_file = os.environ.get('RULES_FILE', '/app/creds/tbs_rules.yaml')
    config = Config(rules_file)
    api = login(config)
    
    simulation = SimulationManager(config, api)
    
    start_time_str = config.get_rule('start_time')
    start_time = datetime.strptime(start_time_str, '%H:%M:%S').time()
    now = datetime.now()
    today_start_time = datetime.combine(now.date(), start_time)
    
    if now > today_start_time:
        start_datetime = today_start_time + timedelta(days=1)
    else:
        start_datetime = today_start_time

    delay = (start_datetime - now).total_seconds()
    
    if delay > 0:
        app_logger.info(f"Waiting for {delay:.2f} seconds until start time: {start_time_str}")
        # await asyncio.sleep(delay)
    
    await simulation.run()

if __name__ == "__main__":
    asyncio.run(main())