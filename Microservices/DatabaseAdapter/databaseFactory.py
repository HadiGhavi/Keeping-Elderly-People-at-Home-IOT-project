import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
from datetime import datetime
from typing import Dict, Any, Optional
from adapterInterface import TimeSeriesAdapter
from influxdbAdapter import InfluxDBAdapter

class DatabaseConfig:
    """Manages database configuration from file or environment variables"""
    
    def __init__(self, config_file: str = "database_config.json"):
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                return json.load(f)
        else:
            # Create default configuration
            default_config = {
                "active_adapter": "influxdb",
                "adapters": {
                    "influxdb": {
                        "host": "https://eu-central-1-1.aws.cloud2.influxdata.com",
                        "token": "WaCTN7nEqIMjNSsl-Yzry1iz6Os2F4xskPWrdrA5JQe49JmxT0MiUtOgvAHtz94cTkVolVrcplxYXfaYxqPf-g==",
                        "org": "Dev Team",
                        "bucket": "iot_health"
                    }
                }
            }
            self._save_config(default_config)
            return default_config
    
    def _save_config(self, config: Dict[str, Any]):
        """Save configuration to file"""
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=4)
    
    def get_active_adapter_config(self) -> tuple[str, Dict[str, Any]]:
        """Get the configuration for the currently active adapter"""
        active_adapter = self.config.get("active_adapter", "influxdb")
        adapter_config = self.config.get("adapters", {}).get(active_adapter, {})
        return active_adapter, adapter_config
    
    def set_active_adapter(self, adapter_name: str):
        """Change the active adapter"""
        if adapter_name in self.config.get("adapters", {}):
            self.config["active_adapter"] = adapter_name
            self._save_config(self.config)
        else:
            raise ValueError(f"Adapter '{adapter_name}' not configured")
    
    def get_available_adapters(self) -> list[str]:
        """Get list of configured adapter names"""
        return list(self.config.get("adapters", {}).keys())


class DatabaseAdapterFactory:
    """Factory class to create appropriate database adapter instances"""
    
    _adapters = {
        "influxdb": InfluxDBAdapter
    }
    
    @classmethod
    def create_adapter(cls, adapter_name: str, config: Dict[str, Any]) -> TimeSeriesAdapter:
        """
        Create a database adapter instance.
        
        Args:
            adapter_name: Name of the adapter to create
            config: Configuration dictionary for the adapter
            
        Returns:
            TimeSeriesAdapter instance
            
        Raises:
            ValueError: If adapter_name is not supported
        """
        if adapter_name not in cls._adapters:
            available = ", ".join(cls._adapters.keys())
            raise ValueError(f"Unsupported adapter '{adapter_name}'. Available: {available}")
        
        adapter_class = cls._adapters[adapter_name]
        return adapter_class(config)
    
    @classmethod
    def register_adapter(cls, name: str, adapter_class: type):
        """Register a new adapter class"""
        if not issubclass(adapter_class, TimeSeriesAdapter):
            raise ValueError("Adapter class must inherit from TimeSeriesAdapter")
        cls._adapters[name] = adapter_class
    
    @classmethod
    def get_available_adapters(cls) -> list[str]:
        """Get list of available adapter types"""
        return list(cls._adapters.keys())

    
class DatabaseService:
    def __init__(self, config=None):
        print("=== DatabaseService.__init__ called ===")
        print(f"Config parameter: {config}")
        
        if config is None:
            print("Loading config from Config.DATABASE")
            from config import Config
            config = Config.DATABASE
            print(f"Loaded config: {config}")
        
        self.config_data = config
        self.adapter = None
        print("About to call _initialize_adapter")
        self._initialize_adapter()
        print(f"Initialization complete. Adapter: {self.adapter}")

    def _initialize_adapter(self):
        print("DatabaseService: _initialize_adapter called")
        adapter_name = self.config_data.get("active_adapter")
        print(f"DatabaseService: Active adapter: {adapter_name}")
        
        adapter_config = self.config_data.get("adapters", {}).get(adapter_name)
        print(f"DatabaseService: Adapter config: {adapter_config}")
        
        if not adapter_config:
            print(f"No configuration found for adapter: {adapter_name}")
            return
        
        try:
            print(f"DatabaseService: Creating adapter '{adapter_name}' with config")
            self.adapter = DatabaseAdapterFactory.create_adapter(adapter_name, adapter_config)
            print(f"DatabaseService: Adapter created: {self.adapter}")
            
            print("DatabaseService: Attempting to connect...")
            connected = self.adapter.connect()
            print(f"DatabaseService: Connection result: {connected}")
            
            if not connected:
                print(f"Warning: Failed to connect to {adapter_name}")
                self.adapter = None
            else:
                print(f"Successfully connected to {adapter_name}")
                
        except Exception as e:
            print(f"Error initializing {adapter_name} adapter: {e}")
            import traceback
            traceback.print_exc()
            self.adapter = None
    
    def write_health_data(self, user_id: str, user_name: str, 
                        temp: float, heart_rate: int, oxygen: float, state: str) -> tuple[bool, str]:
        print(f"write_health_data called, adapter status: {self.adapter is not None}")
        
        if not self.adapter:
            print("write_health_data: No database adapter available")
            return False, "No database adapter available"
        
        data = {
            "tags": {
                "UserId": user_id,
                "full_name": user_name
            },
            "fields": {
                "temp": temp,
                "heart_rate": heart_rate,
                "oxygen": oxygen,
                "state": state
            }
        }
        
        return self.adapter.write_data("value", data)
    
    def get_all_users(self) -> tuple[bool, list]:
        """Get all users who have data in the system"""
        if not self.adapter:
            return False, []
        
        success, result = self.adapter.get_all_users()
        if success:
            return True, result
        else:
            return False, []
        
    def get_user_health_data(self, user_id: str, time_range: Optional[Dict[str, datetime]] = None) -> tuple[bool, list]:
        """Get all health data for a user with optional time filtering"""
        print(f"DEBUG: DatabaseService.get_user_health_data called with user_id={user_id}, time_range={time_range}")
        
        if not self.adapter:
            print("DEBUG: No adapter available")
            return False, []
        
        success, result = self.adapter.get_user_data(user_id, time_range)
        print(f"DEBUG: Adapter returned: success={success}, result_type={type(result)}")
    
        if success:
            return True, result
        else:
            print(f"DEBUG: Adapter failed with message: {result}")
            return False, []
    
    def delete_user_data(self, user_id: str) -> tuple[bool, str]:
        """Delete all data for a user"""
        if not self.adapter:
            return False, "No database adapter available"
        
        return self.adapter.delete_user_data(user_id)
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get information about the current database"""
        if not self.adapter:
            return {"error": "No adapter available"}
        
        return self.adapter.get_database_info()
    
    def switch_adapter(self, adapter_name: str) -> bool:
        """Switch to a different database adapter"""
        try:
            if self.adapter:
                self.adapter.disconnect()
            
            if self.config_manager:
                self.config_manager.set_active_adapter(adapter_name)
                self._initialize_adapter()
            else:
                # Direct config - can't switch dynamically
                return False
            
            return self.adapter is not None
            
        except Exception as e:
            print(f"Error switching to {adapter_name}: {e}")
            return False

    def get_available_adapters(self) -> list[str]:
        """Get list of available database adapters"""
        if self.config_manager:
            return self.config_manager.get_available_adapters()
        else:
            return list(self.config_data.get("adapters", {}).keys())


# Example usage and testing
if __name__ == "__main__":
    # Initialize database service
    db_service = DatabaseService()
    
    # Get database info
    info = db_service.get_database_info()
    print(f"Current database: {info}")
