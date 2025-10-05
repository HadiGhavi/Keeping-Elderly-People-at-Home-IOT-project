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
        self.notification_service_url = self.registry.get_service_url("notification")
        
        # Get full MQTT service info 
        self.mqtt_service_info = self.registry.get_service_info("mqtt")
        
        # Load ML model
        try:
            self.predict = HealthStatePredictor(Config.CLASSIFICATION["TRAINMODEL"])
        except (FileNotFoundError, ImportError) as e:
            print(f"Warning: Could not load ML model: {e}")
            self.predict = MockPredictor()
        
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
        """Process incoming MQTT messages using the database adapter"""
        try:
            json_message = json.loads(message)
            measurement = topic.split("/")[-1]
            
            # Extract sensor values with flexible matching
            available_sensors = {sensor["name"]: sensor for sensor in json_message["sensors"]}
            
            temp_value = None
            oxygen_value = None
            heart_rate_value = None
            
            # Look for temperature sensor
            for sensor_name, sensor_data in available_sensors.items():
                if "temp" in sensor_name.lower():
                    temp_value = float(sensor_data["value"])
                    break
            
            # Look for oxygen sensor  
            for sensor_name, sensor_data in available_sensors.items():
                if "oxygen" in sensor_name.lower() or "spo2" in sensor_name.lower():
                    oxygen_value = float(sensor_data["value"])
                    break
                    
            # Look for heart rate sensor
            for sensor_name, sensor_data in available_sensors.items():
                if "heart" in sensor_name.lower() or "pulse" in sensor_name.lower():
                    heart_rate_value = int(float(sensor_data["value"]))
                    break

            # Use realistic defaults only if sensors are completely missing
            if temp_value is None:
                print("INFO: No temperature sensor configured for this user")
                temp_value = 36.5
                
            if oxygen_value is None:
                print("INFO: No oxygen sensor configured for this user")
                oxygen_value = 98.0
                
            if heart_rate_value is None:
                print("INFO: No heart rate sensor configured for this user") 
                heart_rate_value = 75

            print(f"Final values - temp: {temp_value}, oxygen: {oxygen_value}, heart_rate: {heart_rate_value}")
            
            # Predict health state
            predicted_state = self.predict.predict_state(temp_value, heart_rate_value, oxygen_value)
            print(f"Predicted state: {predicted_state}")

            # Send notifications if needed
            if predicted_state in ["risky", "dangerous"]:
                print(f"Alert triggered: User {json_message['user_id']} ({json_message['user_name']}) - State: {predicted_state}")
                
                try:
                    user_response = requests.get(f"{self.catalog_url}/users/{json_message['user_id']}")
                    if user_response.status_code == 200:
                        user_info = user_response.json()
                        assigned_doctor_id = user_info.get('doctor_id')
                        print(f"Patient {json_message['user_id']} assigned doctor: {assigned_doctor_id}")
                        
                        # Prepare notification data
                        notification_data = {
                            "user_id": json_message["user_id"],
                            "user_name": json_message["user_name"],
                            "state": predicted_state,
                            "temp": temp_value,
                            "oxygen": oxygen_value,
                            "heartRate": heart_rate_value
                        }
                        
                        # Patient notification
                        patient_notification = {**notification_data, "recipient_type": "patient"}
                        response = requests.post(
                            f"{self.notification_service_url}/sendNotif", 
                            json=patient_notification
                        )                        
                        print(f"Patient notification sent to {json_message['user_id']} - Status: {response.status_code}")
                        
                        # Doctor notification if assigned
                        if assigned_doctor_id:
                            doctor_notification = {
                                **notification_data, 
                                "recipient_type": "doctor", 
                                "doctor_id": assigned_doctor_id, 
                                "patient_name": json_message["user_name"]
                            }
                            doctor_response = requests.post(
                                f"{self.notification_service_url}/sendNotif", 
                                json=doctor_notification
                            )                           
                            print(f"Doctor notification sent to {assigned_doctor_id} - Status: {doctor_response.status_code}")
                        else:
                            print("No doctor assigned to this patient")
                            
                except Exception as e:
                    print(f"Error sending notifications: {e}")

            # Store in database using the service
            print("Starting database write...")
            success, message = self._write_health_data(
                user_id=json_message["user_id"],
                user_name=json_message["user_name"],
                temp=temp_value,
                heart_rate=heart_rate_value,
                oxygen=oxygen_value,
                state=predicted_state
            )
            
            print(f"Database write result: {message}")
            return success
            
        except ValueError:
            print(f"Invalid message format: {message}")
            return False
        except Exception as e:
            print(f"Processing error: {e}")
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