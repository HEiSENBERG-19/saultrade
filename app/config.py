import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class Config:
    def __init__(self, rules_file: str):
        load_dotenv()
        self._rules: Dict[str, Any] = self._load_rules(rules_file)

    def _load_rules(self, file_path: str) -> Dict[str, Any]:
        import yaml
        if not os.path.exists(file_path):
            logger.error(f"Rules file not found: {file_path}")
            return {}
        try:
            with open(file_path, 'r') as file:
                return yaml.safe_load(file)
        except Exception as e:
            logger.error(f"Error loading rules from {file_path}: {e}", exc_info=True)
            return {}

    def get_config(self, key: str, default: Optional[Any] = None) -> Any:
        return os.environ.get(key, default)
    
    def get_rule(self, key: str, default: Optional[Any] = None) -> Any:
        return self._rules.get(key, default)

    def get_redis_config(self) -> Dict[str, Any]:
        return {
            "host": os.environ.get("REDIS_HOST", "localhost"),
            "port": int(os.environ.get("REDIS_PORT", 6379)),
        }

    def get_influxdb_config(self) -> Dict[str, Any]:
        return {
            "url": os.environ.get("INFLUXDB_URL"),
            "token": os.environ.get("INFLUXDB_TOKEN"),
            "org": os.environ.get("INFLUXDB_ORG"),
            "bucket": os.environ.get("INFLUXDB_BUCKET"),
        }

    def get_user_credentials(self) -> Dict[str, str]:
        return {
            "user": os.environ.get("API_USER"),
            "pwd": os.environ.get("API_PWD"),
            "vc": os.environ.get("API_VC"),
            "app_key": os.environ.get("API_KEY"),
            "secret": os.environ.get("API_SECRET"),
            "imei": os.environ.get("API_IMEI"),
        }

    def get_simulation_duration(self) -> int:
        return int(os.environ.get("SIMULATION_DURATION", 60))