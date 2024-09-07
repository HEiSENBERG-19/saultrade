import yaml
import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class Config:
    def __init__(self, config_file: str, rules_file: str):
        self._config: Dict[str, Any] = self._load_config(config_file)
        self._rules: Dict[str, Any] = self._load_config(rules_file)

    def _load_config(self, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            logger.error(f"Configuration file not found: {file_path}")
            return {}

        try:
            with open(file_path, 'r') as file:
                return yaml.safe_load(file)
        except Exception as e:
            logger.error(f"Error loading configuration from {file_path}: {e}", exc_info=True)
            return {}

    def get_config(self, key: str, default: Optional[Any] = None) -> Any:
        return self._config.get(key, default)
    
    def get_rule(self, key: str, default: Optional[Any] = None) -> Any:
        return self._rules.get(key, default)

    def get_redis_config(self) -> Dict[str, Any]:
        return self._config.get('redis', {})

    def get_influxdb_config(self) -> Dict[str, Any]:
        return self._config.get('influxdb', {})

    def get_simulation_duration(self) -> int:
        return self._config.get('simulation_duration', 60)