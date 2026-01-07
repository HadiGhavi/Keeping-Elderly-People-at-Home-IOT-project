import time
import json
import threading
import requests
import os
import pickle
import traceback
import numpy as np
from datetime import datetime
from MyMQTT import MyMQTT 
from Microservices.Common.config import Config
from Microservices.Common.utils import ServiceRegistry
from ClassificationAlgorithm.HealthStatePredictor import HealthStatePredictor

class MockPredictor:
    def predict_state(self, temp, heart_rate, oxygen):
        if temp > 39 or heart_rate > 100 or oxygen < 90: return "dangerous"
        elif temp > 37.5 or heart_rate > 90 or oxygen < 95: return "risky"
        else: return "healthy"

class RetrainedPredictor:
    def __init__(self, model): self.model = model
    def predict_state(self, temp, heart_rate, oxygen):
        features = np.array([[temp, heart_rate, oxygen]])
        return self.model.predict(features)[0]

class DataHandlerAdapter:
    def __init__(self):
        self.registry = ServiceRegistry()
        self.catalog_url = Config.SERVICES["catalog_url"]
        self.database_service_url = self.registry.get_service_url("databaseAdapter")
        self.mqtt_info = self.registry.get_service_info("mqtt")
        
        # Load Predictor
        self.predict = self._load_model()
        
        # Cache and Threading
        self.user_sensor_cache = {}
        self.cache_timeout = 120
        self.cache_lock = threading.Lock()
        
        # Retraining Config
        self.retrain_interval = 900
        self.last_retrain_time = time.time()
        self.min_samples_for_retrain = 100
        self.model_save_path = Config.CLASSIFICATION.get("TRAINMODEL", "trained_model.pkl")

        # Initialize MyMQTT with 'self' as the notifier
        self.mqtt_client = MyMQTT(
            clientID="DataIngestionService", 
            broker=self.mqtt_info["url"], 
            port=self.mqtt_info["port"], 
            notifier=self 
        )

    def start_services(self):
        """Starts the MQTT connection and background retraining"""
        self.mqtt_client.start() # Connects and starts paho loop
        
        # Subscribe to sensor topics defined in registry
        #for topic in self.mqtt_info["topics"]:
        self.mqtt_client.mySubscribe("iot_user_sensor/value") 
            
        # Start retraining loop
        threading.Thread(target=self._retrain_loop, daemon=True).start()

    def _load_model(self):
        model_path = Config.CLASSIFICATION["TRAINMODEL"]
        if os.path.exists(model_path) and os.path.getsize(model_path) > 0:
            try: return HealthStatePredictor(model_path)
            except: return MockPredictor()
        return MockPredictor()

    def notify(self, topic, payload):
        """REQUIRED by MyMQTT: Bridges to processing logic"""
        try:
            # Pass the raw payload to your existing processing method
            self.process_mqtt_message(topic, payload)
        except Exception as e:
            print(f"Error in MyMQTT notify: {e}")

    def process_mqtt_message(self, topic, message):
        """Processes incoming sensor data from Monitor"""
        try:
            msg = json.loads(message)
            user_id = str(msg["user_id"])
            user_name = msg["user_name"]
            now = time.time()
            print(f"Received data from user {user_id} with vitals {msg}")
            with self.cache_lock:
                if user_id not in self.user_sensor_cache: 
                    self.user_sensor_cache[user_id] = {}
                
                # Handle monitor data format (list of sensors)
                for s in msg["sensors"]:
                    self.user_sensor_cache[user_id][s["name"]] = {
                        "value": s["value"], 
                        "timestamp": now
                    }
                
                cache = self.user_sensor_cache[user_id]
                vals = {k: cache[k]["value"] for k in ["temp", "heart_rate", "oxygen"] 
                        if k in cache and (now - cache[k]["timestamp"]) <= self.cache_timeout}

            # If we have all 3 vitals, predict and potentially alert
            if len(vals) == 3:
                state = self.predict.predict_state(
                    float(vals["temp"]), 
                    int(float(vals["heart_rate"])), 
                    float(vals["oxygen"])
                )
                
                # Write to DB
                self._write_to_db(user_id, user_name, vals["temp"], vals["heart_rate"], vals["oxygen"], state)
                
                # Event-Driven Alert using MyMQTT
                if state in ["risky", "dangerous"]:
                    alert_payload = json.dumps({
                        "user_id": user_id,
                        "user_name": user_name,
                        "state": state,
                        "vitals": vals # Flat dict of floats
                    })
                    self.mqtt_client.myPublish(f"iot/notifications/{state}", alert_payload)  
                    print(f"Alert published for user {user_id} with state {state}")    
        except Exception as e: 
            print(f"Processing error: {e}")

    def _write_to_db(self, uid, name, t, hr, ox, state):
        payload = {"user_id": uid, "user_name": name, "temp": t, "heart_rate": hr, "oxygen": ox, "state": state}
        requests.post(f"{self.database_service_url}/write", json=payload, timeout=5)

    def _retrain_loop(self):
        """Continuously retrain the model with new data at fixed intervals"""
        print("Model retraining loop started")
        while True:
            try:
                # Wait for the retrain interval (e.g., 15 minutes)
                time.sleep(self.retrain_interval)
                
                current_time = time.time()
                print(f"Attempting model retraining...")
                
                # Perform retraining
                success = self._retrain_model()
                
                if success:
                    self.last_retrain_time = current_time
                    print(f"Model retrained successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    print(f"Model retraining skipped (not enough data or failed)")
                    
            except Exception as e:
                print(f"Error in retraining loop: {e}")
                traceback.print_exc()

    def _retrain_model(self):
        """Retrain the ML model using recent database data"""
        try:
            # 1. Fetch all users from catalog to identify patients
            users_response = requests.get(f"{self.catalog_url}/users", timeout=5)
            if users_response.status_code != 200:
                return False
            
            users = users_response.json()
            patients = [u for u in users if u.get("user_type") == "patient"]
            
            # 2. Collect historical data from all patients
            all_data = []
            for patient in patients:
                user_id = patient["user_chat_id"]
                try:
                    # Get last 7 days of data for training
                    data_res = requests.get(
                        f"{self.database_service_url}/read/{user_id}",
                        params={"hours": 168}, 
                        timeout=15
                    )
                    if data_res.status_code == 200:
                        result = data_res.json()
                        if result.get("success") and result.get("data"):
                            all_data.extend(result["data"])
                except Exception:
                    continue
            
            # 3. Validation: Ensure we have enough data
            if len(all_data) < self.min_samples_for_retrain:
                print(f"Not enough data: {len(all_data)} samples")
                return False
            
            # 4. Prepare data and Train
            X, y = self._prepare_training_data(all_data)
            if X is not None:
                new_model = self._train_classifier(X, y)
                if new_model:
                    self._save_model(new_model)
                    self.predict = new_model # Update active predictor
                    return True
            return False
            
        except Exception as e:
            print(f"Error during model retraining: {e}")
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
            print(f"Validation accuracy: {val_score:.2%}")
            
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
            
            print(f"Model saved successfully to {self.model_save_path}")
            
        except Exception as e:
            print(f"Error saving model: {e}")
            import traceback
            traceback.print_exc()
            
            # Clean up temp file if it exists
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass

