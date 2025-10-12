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
import pickle
import os
import numpy as np
from sklearn.ensemble import RandomForestClassifier 
from datetime import datetime, timedelta
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

class RetrainedPredictor:
    def __init__(self, model):
        self.model = model
    
    def predict_state(self, temp, heart_rate, oxygen):
        features = np.array([[temp, heart_rate, oxygen]])
        prediction = self.model.predict(features)[0]
        return prediction
        
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
            model_path = Config.CLASSIFICATION["TRAINMODEL"]
            
            # Check if file exists and is not empty
            if os.path.exists(model_path) and os.path.getsize(model_path) > 0:
                try:
                    self.predict = HealthStatePredictor(model_path)
                    print(f"✅ Loaded ML model from {model_path}")
                except (EOFError, pickle.UnpicklingError) as e:
                    print(f"⚠️ Model file corrupted: {e}. Using MockPredictor.")
                    self.predict = MockPredictor()
            else:
                print(f"⚠️ Model file not found or empty. Using MockPredictor.")
                self.predict = MockPredictor()
                
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

        # Model retraining configuration
        self.retrain_interval = 900  # Retrain every 15 minutes
        self.last_retrain_time = time.time()
        self.min_samples_for_retrain = 100  # Minimum samples needed to retrain
        self.model_save_path = Config.CLASSIFICATION.get("TRAINMODEL", "trained_model.pkl")

        # Start retraining thread
        print("🔄 Starting model retraining service...")
        retrain_thread = threading.Thread(target=self.model_retraining_loop, daemon=True)
        retrain_thread.start()
    
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
    
    def model_retraining_loop(self):
        """Continuously retrain the model with new data"""
        print("🔄 Model retraining loop started")
        
        while True:
            try:
                # Wait for the retrain interval
                time.sleep(self.retrain_interval)
                
                current_time = time.time()
                time_since_last_retrain = current_time - self.last_retrain_time
                
                print(f"🔄 Attempting model retraining (last trained {time_since_last_retrain/60:.1f} minutes ago)")
                
                # Perform retraining
                success = self._retrain_model()
                
                if success:
                    self.last_retrain_time = current_time
                    print(f"✅ Model retrained successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    print(f"⚠️ Model retraining skipped or failed")
                    
            except Exception as e:
                print(f"❌ Error in retraining loop: {e}")
                import traceback
                traceback.print_exc()

    def _retrain_model(self):
        """Retrain the ML model using recent database data"""
        try:
            print("📊 Fetching training data from database...")
            
            # Get all users
            users_response = requests.get(f"{self.catalog_url}/users", timeout=5)
            if users_response.status_code != 200:
                print("⚠️ Could not fetch users from catalog")
                return False
            
            users = users_response.json()
            patients = [u for u in users if u.get("user_type") == "patient"]
            
            # Collect data from all patients (last 7 days for training)
            all_data = []
            for patient in patients:
                user_id = patient["user_chat_id"]
                
                try:
                    # Get last 7 days of data
                    data_response = requests.get(
                        f"{self.database_service_url}/read/{user_id}",
                        params={"hours": 168},  # 7 days
                        timeout=15
                    )
                    
                    if data_response.status_code == 200:
                        result = data_response.json()
                        if result.get("success") and result.get("data"):
                            all_data.extend(result["data"])
                except Exception as e:
                    print(f"⚠️ Error fetching data for user {user_id}: {e}")
                    continue
            
            if len(all_data) < self.min_samples_for_retrain:
                print(f"⚠️ Not enough data for retraining: {len(all_data)} samples (need {self.min_samples_for_retrain})")
                return False
            
            print(f"📊 Collected {len(all_data)} data points from {len(patients)} patients")
            
            # Prepare training data
            X_train, y_train = self._prepare_training_data(all_data)
            
            if X_train is None or len(X_train) == 0:
                print("⚠️ No valid training data after preparation")
                return False
            
            print(f"🎯 Training with {len(X_train)} complete samples")
            
            # Train new model
            new_model = self._train_classifier(X_train, y_train)
            
            if new_model is None:
                print("❌ Model training failed")
                return False
            
            # Save the new model
            self._save_model(new_model)
            
            # Replace the current predictor
            self.predict = new_model
            
            print(f"✅ Model updated and saved to {self.model_save_path}")
            return True
            
        except Exception as e:
            print(f"❌ Error during model retraining: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _prepare_training_data(self, data):
        """Convert database records to training format"""
        try:
            # Group data by time to get complete records
            from collections import defaultdict
            
            records = defaultdict(dict)
            
            for entry in data:
                time_key = entry.get("time")
                field = entry.get("field")
                value = entry.get("value")
                
                if time_key and field:
                    records[time_key][field] = value
            
            # Extract complete samples (with temp, heart_rate, oxygen, and state)
            X_train = []
            y_train = []
            
            for time_key, record in records.items():
                if all(field in record for field in ["temp", "heart_rate", "oxygen", "state"]):
                    try:
                        temp = float(record["temp"])
                        heart_rate = float(record["heart_rate"])
                        oxygen = float(record["oxygen"])
                        state = str(record["state"])
                        
                        X_train.append([temp, heart_rate, oxygen])
                        y_train.append(state)
                    except (ValueError, TypeError) as e:
                        continue
            
            if len(X_train) == 0:
                return None, None
            
            return np.array(X_train), np.array(y_train)
            
        except Exception as e:
            print(f"Error preparing training data: {e}")
            return None, None

    def _train_classifier(self, X_train, y_train):
        """Train a new classifier model"""
        try:
            # Use the same model architecture as your HealthStatePredictor
            # Adjust this based on your actual model
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.model_selection import train_test_split
            
            # Split for validation
            X_train_split, X_val, y_train_split, y_val = train_test_split(
                X_train, y_train, test_size=0.2, random_state=42
            )
            
            # Train model
            model = RandomForestClassifier(
                n_estimators=100,
                random_state=42,
                class_weight='balanced' 
            )
            
            model.fit(X_train_split, y_train_split)
            
            # Validate
            val_score = model.score(X_val, y_val)
            print(f"📈 Validation accuracy: {val_score:.2%}")
            
            return RetrainedPredictor(model)
            
        except Exception as e:
            print(f"Error training classifier: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _save_model(self, predictor):
        """Save the trained model to disk"""
        try:
            # Extract the sklearn model from the wrapper
            sklearn_model = predictor.model
            
            # Save to a temporary file first (atomic write)
            temp_path = self.model_save_path + '.tmp'
            
            with open(temp_path, 'wb') as f:
                pickle.dump(sklearn_model, f)
            
            # Only replace the original file if write was successful
            import os
            import shutil
            shutil.move(temp_path, self.model_save_path)
            
            print(f"💾 Model saved successfully to {self.model_save_path}")
            
        except Exception as e:
            print(f"❌ Error saving model: {e}")
            import traceback
            traceback.print_exc()
            
            # Clean up temp file if it exists
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass

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