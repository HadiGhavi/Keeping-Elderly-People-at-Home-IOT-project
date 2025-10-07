import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from ClassificationAlgorithm.HealthStatePredictor import HealthStatePredictor
from Microservices.DataIngestion.mqttConnector import MQTTService
from Microservices.Common.config import Config
import time
import json
import cherrypy
import requests
import threading
import webbrowser
from Microservices.Common.utils import (
    register_service_with_catalog,
    ServiceRegistry
)

class MockPredictor:
    """Simple mock predictor for testing"""
    def predict_state(self, temp, heart_rate, oxygen):
        # Simple rule-based prediction
        if temp > 39 or heart_rate > 100 or oxygen < 90:
            return "dangerous"
        elif temp > 37.5 or heart_rate > 90 or oxygen < 95:
            return "risky"
        else:
            return "normal"

        
class DataHandler:
    def __init__(self):
        """Initialize DataHandler with service discovery"""
        # Store catalog URL
        self.catalog_url = Config.SERVICES["catalog_url"]
        
        self.registry = ServiceRegistry()
        # Discover service URLs at initialization
        self.database_service_url = self.registry.get_service_url("databaseAdapter")
        
        # Get full MQTT service info 
        self.mqtt_service_info = self.registry.get_service_info("mqtt")
        
        # Load ML model
        try:
            self.predict = HealthStatePredictor(Config.CLASSIFICATION["TRAINMODEL"])
        except (FileNotFoundError, ImportError) as e:
            print(f"Warning: Could not load ML model: {e}")
            self.predict = MockPredictor()
        
        # Cache for storing latest sensor values per user
        self.user_sensor_cache = {}  # user_id -> {sensor_type: {"value": val, "timestamp": time}}
        self.cache_timeout = 120  # Cache values for 2 minutes
        self.cache_lock = threading.Lock()
        
        # Test database connection
        self._test_database_connection()
        
        # Start MQTT automatically
        print("Starting MQTT subscriber...")
        background_thread = threading.Thread(target=self.main, daemon=True)
        background_thread.start()
    
    def _test_database_connection(self):
        """Test connection to database service"""
        try:
            response = requests.get(f"{self.database_service_url}/info", timeout=5)
            if response.status_code == 200:
                info = response.json()
                print(f"Database service connected: {info.get('database_info', {}).get('adapter_type')}")
            else:
                print(f"Database service responded with status {response.status_code}")
        except Exception as e:
            print(f"Database service not available: {e}")
    
    @cherrypy.expose
    def index(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        return json.dumps({
            "message": "Data handler API - MQTT subscriber running",
            "endpoints": {
                "GET /getUserData/<id>": "get user data from database",
                "GET /database/info": "get database adapter information",
                "POST /database/switch": "switch database adapter"
            },
        }).encode('utf-8')
    
    def _get_user_data(self, user_id: str) -> tuple[bool, list]:
        """Get user health data using the database service"""
        try:
            response = requests.get(
                f"{self.database_service_url}/read/{user_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False), result.get("data", [])
            else:
                return False, []
                
        except Exception as e:
            print(f"Error getting user data: {e}")
            return False, []
    
    @cherrypy.expose
    def getUserData(self, user_id):
        """Get user data using the database service"""
        success, data = self._get_user_data(user_id)
        
        if success:
            return json.dumps(json.dumps(data)).encode('utf-8')
        else:
            return json.dumps([]).encode('utf-8')
    
    @cherrypy.expose 
    def database(self, action=None):
        """Database management endpoint"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        if action == "info":
            try:
                response = requests.get(f"{self.database_service_url}/info")
                return response.content
            except Exception as e:
                return json.dumps({"error": str(e)}).encode('utf-8')
                
        elif action == "switch" and cherrypy.request.method == "POST":
            try:
                request_data = cherrypy.request.body.read()
                response = requests.post(
                    f"{self.database_service_url}/switch",
                    data=request_data,
                    headers={'Content-Type': 'application/json'}
                )
                return response.content
            except Exception as e:
                return json.dumps({"error": str(e)}).encode('utf-8')
        
        elif action == "adapters":
            try:
                response = requests.get(f"{self.database_service_url}/adapters")
                return response.content
            except Exception as e:
                return json.dumps({"error": str(e)}).encode('utf-8')
        
        return json.dumps({"error": "Invalid action"}).encode('utf-8')
    
    def _write_health_data(self, user_id: str, user_name: str, temp: float, 
                          heart_rate: int, oxygen: float, state: str) -> tuple[bool, str]:
        """Write health data using the database service"""
        try:
            data = {
                "user_id": user_id,
                "user_name": user_name,
                "temp": temp,
                "heart_rate": heart_rate,
                "oxygen": oxygen,
                "state": state
            }
            
            response = requests.post(
                f"{self.database_service_url}/write",
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False), result.get("message", "Unknown error")
            else:
                return False, f"Database service error: HTTP {response.status_code}"
                
        except Exception as e:
            return False, f"Error calling database service: {str(e)}"
    
    def process(self, topic: str, message):
        """Process incoming MQTT messages - aggregates sensor data before prediction"""
        try:
            json_message = json.loads(message)
            measurement = topic.split("/")[-1]
            user_id = str(json_message["user_id"])
            user_name = json_message["user_name"]
            
            current_time = time.time()
            
            # Update cache with new sensor values
            with self.cache_lock:
                if user_id not in self.user_sensor_cache:
                    self.user_sensor_cache[user_id] = {}
                
                # Process each sensor in the message
                for sensor in json_message["sensors"]:
                    sensor_type = sensor["name"]  # "temp", "heart_rate", or "oxygen"
                    sensor_value = sensor["value"]
                    
                    self.user_sensor_cache[user_id][sensor_type] = {
                        "value": sensor_value,
                        "timestamp": current_time
                    }
                    print(f"Updated cache for user {user_id}: {sensor_type} = {sensor_value}")
                
                # Get cached values
                cached_data = self.user_sensor_cache[user_id]
                
                # Check if we have all three sensor types with recent values
                required_sensors = ["temp", "heart_rate", "oxygen"]
                available_sensors = {}
                missing_sensors = []
                stale_sensors = []
                
                for sensor_type in required_sensors:
                    if sensor_type in cached_data:
                        # Check if value is still fresh
                        age = current_time - cached_data[sensor_type]["timestamp"]
                        if age <= self.cache_timeout:
                            available_sensors[sensor_type] = cached_data[sensor_type]["value"]
                        else:
                            stale_sensors.append(sensor_type)
                    else:
                        missing_sensors.append(sensor_type)
                
                # Only proceed with prediction if we have all three values
                if len(available_sensors) == 3:
                    temp_value = float(available_sensors["temp"])
                    heart_rate_value = int(float(available_sensors["heart_rate"]))
                    oxygen_value = float(available_sensors["oxygen"])
                    
                    print(f"Processing prediction for user {user_id}:")
                    print(f"  Temp: {temp_value}°C")
                    print(f"  Heart Rate: {heart_rate_value} BPM")
                    print(f"  Oxygen: {oxygen_value}%")
                    
                else:
                    # Not enough data for prediction yet
                    print(f"Waiting for more sensors for user {user_id}:")
                    print(f"  Available: {list(available_sensors.keys())}")
                    if missing_sensors:
                        print(f"  Missing: {missing_sensors}")
                    if stale_sensors:
                        print(f"  Stale (>{self.cache_timeout}s): {stale_sensors}")
                    return False
            
            # Predict health state
            predicted_state = self.predict.predict_state(temp_value, heart_rate_value, oxygen_value)
            print(f"Predicted state: {predicted_state}")

            # Store in database using the service
            print("Writing to database...")
            success, message = self._write_health_data(
                user_id=user_id,
                user_name=user_name,
                temp=temp_value,
                heart_rate=heart_rate_value,
                oxygen=oxygen_value,
                state=predicted_state
            )
            
            print(f"Database write result: {message}")
            return success
            
        except ValueError as e:
            print(f"Invalid message format: {message} - Error: {e}")
            return False
        except Exception as e:
            print(f"Processing error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def main(self):
        """Main MQTT subscriber loop"""
        mqtt_subscriber = MQTTService(
            host=self.mqtt_service_info["url"],
            port=self.mqtt_service_info["port"],
            auth=None
        )
        
        mqtt_subscriber.subscribe(
            topics=self.mqtt_service_info["topics"],
            message_handler=self.process
        )
        
        try:
            while True:
                time.sleep(30)
        except KeyboardInterrupt:
            print("Shutting down...")
            mqtt_subscriber.disconnect()


if __name__ == "__main__":
    # Register the service with catalog 
    register_service_with_catalog(service_name="dataIngestion",
                                  url="http://data_ingestion",
                                  port=2500,
                                  endpoints={
                                      "GET /getUserData/<id>": "get user data from database",
                                      "GET /database/info": "get database adapter information",
                                      "POST /database/switch": "switch database adapter",
                                      "GET /database/adapters": "list available database adapters"
                                  })
    
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 2500,
        'tools.encode.on': True,
        'tools.encode.encoding': 'utf-8'
    })

    def cors():
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"
        cherrypy.response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        cherrypy.response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    
    cherrypy.tools.cors = cherrypy._cptools.HandlerTool(cors)
    conf = {
        '/': {
            'tools.cors.on': True,
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Content-Type', 'application/json')]
        }
    }
    
    webbrowser.open("http://localhost:2500/")
    cherrypy.quickstart(DataHandler(), '/', conf)