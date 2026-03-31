import time
import json
import threading
import requests
import os
import traceback
import numpy as np
import shutil, joblib
from datetime import datetime
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import pandas as pd
from MyMQTT import MyMQTT 
from Microservices.Common.config import Config
from Microservices.Common.utils import ServiceRegistry
from ClassificationAlgorithm.HealthStatePredictor import HealthStatePredictor

class MockPredictor:
    def predict_state(self, temp, heart_rate, oxygen):
        if temp > 39 or heart_rate > 100 or oxygen < 90: return "dangerous"
        elif temp > 37.5 or heart_rate > 90 or oxygen < 95: return "risky"
        else: return "healthy"

class DataHandlerAdapter:
    def __init__(self):
        self.registry = ServiceRegistry()
        self.catalog_url = Config.SERVICES["catalog_url"]
        self.database_service_url = self.registry.get_service_url("databaseAdapter")
        self.mqtt_info = self.registry.get_service_info("mqtt")
        
        self.predictors = {} # Cache HealthStatePredictor instances per user
        self.model_path = Config.CLASSIFICATION["TRAINMODEL"]
        self.feature_columns_list = [] # Updated during retraining
        
        # Cache and Threading
        self.user_sensor_cache = {}
        self.cache_timeout = 120
        self.cache_lock = threading.Lock()
        
        # Retraining Config
        self.retrain_interval = 3600 # 1 Hour
        self.last_retrain_time = time.time()
        self.min_samples_for_retrain = 100
        self.model_save_path = self.model_path
        print("DataHandler initialized (Predictors are per-user)")
        
        # Consecutive Alert Logic
        self.state_counters = {}
        self.last_sent_state = {} 
        self.consecutive_alert_threshold = 5

        self.mqtt_client = MyMQTT(
            clientID="DataIngestionService", 
            broker=self.mqtt_info["url"], 
            port=self.mqtt_info["port"], 
            notifier=self 
        )

    def start_services(self):
        """Starts the MQTT connection and background retraining"""
        self.mqtt_client.start() # Connects and starts paho loop
        
        # Subscribe to sensor topics 
        self.mqtt_client.mySubscribe("iot_user_sensor/value") 
            
        # Start retraining loop
        threading.Thread(target=self._retrain_loop, daemon=True).start()

    def _get_predictor(self, user_id):
        """Retrieve or initialize a predictor for a specific user"""
        if user_id not in self.predictors:
            if os.path.exists(self.model_path) and os.path.getsize(self.model_path) > 0:
                try: 
                    self.predictors[user_id] = HealthStatePredictor(self.model_path)
                    print(f"Loaded HealthStatePredictor instance for user {user_id}")
                except Exception as e: 
                    print(f"Falling back to MockPredictor for user {user_id}: {e}")
                    self.predictors[user_id] = MockPredictor()
            else:
                self.predictors[user_id] = MockPredictor()
        return self.predictors[user_id]

    def notify(self, topic, payload):
        """REQUIRED by MyMQTT"""
        try:
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
            #print(f"Received data from user {user_id} with vitals {msg}")
            with self.cache_lock:
                if user_id not in self.user_sensor_cache: 
                    self.user_sensor_cache[user_id] = {}
                
                for s in msg["sensors"]:
                    self.user_sensor_cache[user_id][s["name"]] = {
                        "value": s["value"], 
                        "timestamp": now
                    }
                
                cache = self.user_sensor_cache[user_id]
                vals = {k: cache[k]["value"] for k in ["temp", "heart_rate", "oxygen"] 
                        if k in cache and (now - cache[k]["timestamp"]) <= self.cache_timeout}

            # If we have all 3 vitals, predict 
            if len(vals) == 3:
                predictor = self._get_predictor(user_id)
                state = predictor.predict_state(
                    float(vals["temp"]), 
                    int(float(vals["heart_rate"])), 
                    float(vals["oxygen"])
                )
                print(f"Predicted state for user {user_id}: {state}")                
                self._write_to_db(user_id, user_name, vals["temp"], vals["heart_rate"], vals["oxygen"], state)
                
                if state in ["risky", "dangerous"]:
                    self.state_counters[user_id] = self.state_counters.get(user_id, 0) + 1
                    
                    # Only publish if threshold reached AND either:
                    # 1. State changed since last sent (e.g. risky -> dangerous)
                    # 2. Threshold was just exactly hit (to avoid double publication before notif cooldown)
                    should_publish = (
                        self.state_counters[user_id] >= self.consecutive_alert_threshold and
                        self.last_sent_state.get(user_id) != state
                    )

                    if should_publish:
                        self.last_sent_state[user_id] = state
                        alert_payload = json.dumps({
                            "user_id": user_id,
                            "user_name": user_name,
                            "state": state,
                            "vitals": vals 
                        })
                        self.mqtt_client.myPublish(f"iot/notifications/{state}", alert_payload)  
                        print(f"Message published for user {user_id} with state {state} ({self.state_counters[user_id]} consecutive)")
                    else:
                        status_msg = f"suppressed ({self.state_counters[user_id]}/{self.consecutive_alert_threshold})"
                        if self.state_counters[user_id] >= self.consecutive_alert_threshold:
                            status_msg = f"throttled (already sent {state})"
                        print(f"State {state} detected for {user_id}, {status_msg}")
                else:
                    # Healthy -> Reset counter and last sent
                    self.state_counters[user_id] = 0
                    self.last_sent_state[user_id] = None
        except Exception as e: 
            print(f"Processing error: {e}")

    def _write_to_db(self, uid, name, t, hr, ox, state):
        payload = {"user_id": uid, "user_name": name, "temp": t, "heart_rate": hr, "oxygen": ox, "state": state}
        requests.post(f"{self.database_service_url}/write", json=payload, timeout=5)

    def _retrain_loop(self):
        print("Model retraining loop started")
        while True:
            try:
                time.sleep(self.retrain_interval)
                
                current_time = time.time()
                print(f"Attempting model retraining...")
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
            
            # 3. Ensure we have enough data
            if len(all_data) < self.min_samples_for_retrain:
                print(f"Not enough data: {len(all_data)} samples")
                return False
            
            # 4. Train
            X, y = self._prepare_training_data(all_data)
            if X is not None:
                new_model_info = self._train_classifier(X, y)
                if new_model_info:
                    self._save_model(new_model_info)
                    # Clear predictors to force re-loading of the new model
                    self.predictors = {}
                    return True
            return False
            
        except Exception as e:
            print(f"Error during model retraining: {e}")
            return False
        
    def _prepare_training_data(self, data):
        try:
            # Group data by time to get complete records
            df = pd.DataFrame(data)
            df = df.pivot(index=['user_id', 'time'], columns='field', values='value').reset_index()
            
            # Map column names if they differ
            df = df.rename(columns={'temp': 'temperature'})
            
            # Check for required fields
            required_vitals = ['temperature', 'heart_rate', 'oxygen']
            if not all(field in df.columns for field in required_vitals + ['state']):
                return None, None
                
            # Convert to numeric
            for col in required_vitals:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna(subset=required_vitals + ['state'])
            df = df.sort_values(['user_id', 'time'])
            
            # Feature Engineering (Temporal Patterns)
            df['hr_diff'] = df.groupby('user_id')['heart_rate'].diff().fillna(0)
            df['spo2_diff'] = df.groupby('user_id')['oxygen'].diff().fillna(0)
            df['temp_diff'] = df.groupby('user_id')['temperature'].diff().fillna(0)
            
            feature_cols = ['temperature', 'heart_rate', 'oxygen', 'hr_diff', 'spo2_diff', 'temp_diff']
            
            # Add Rolling Windows (Temporal Patterns)
            windows = [5, 10]
            for w in windows:
                for col in ['temperature', 'heart_rate', 'oxygen']:
                    df[f'{col}_roll_mean_{w}'] = df.groupby('user_id')[col].transform(lambda x: x.rolling(w, min_periods=1).mean())
                    df[f'{col}_roll_std_{w}'] = df.groupby('user_id')[col].transform(lambda x: x.rolling(w, min_periods=1).std().fillna(0))
                    feature_cols.append(f'{col}_roll_mean_{w}')
                    feature_cols.append(f'{col}_roll_std_{w}')
            
            # Prepare X and y
            X = df[feature_cols].values
            y = df['state'].values
            
            self.feature_columns_list = feature_cols # Store for _train_classifier
            
            return X, y
            
        except Exception as e:
            print(f"Error preparing training data: {e}")
            import traceback
            traceback.print_exc()
            return None, None

    def _train_classifier(self, X_train, y_train):
        try:
            # Encode labels
            label_encoder = LabelEncoder()
            y_train_encoded = label_encoder.fit_transform(y_train)
            
            # Split for validation
            X_train_split, X_val, y_train_split, y_val = train_test_split(
                X_train, y_train_encoded, test_size=0.2, random_state=42
            )
            
            model = xgb.XGBClassifier(
                n_estimators=500,
                learning_rate=0.05,
                max_depth=7,
                eval_metric='mlogloss',
                random_state=42
            )
            
            model.fit(X_train_split, y_train_split)
            
            # Validate
            val_score = model.score(X_val, y_val)
            print(f"Validation accuracy (online): {val_score:.2%}")
            
            model_info = {
                'model': model,
                'feature_columns': self.feature_columns_list,
                'label_encoder': label_encoder,
                'accuracy': val_score
            }
            
            return model_info
            
        except Exception as e:
            print(f"Error training classifier: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _save_model(self, model_info):
        try:
            # Save to a temporary file first
            temp_path = self.model_save_path + '.tmp'
            
            joblib.dump(model_info, temp_path)
            
            # Replace the original file if write was successful
            shutil.move(temp_path, self.model_save_path)
            
            print(f"Model saved successfully to {self.model_save_path}")
            
        except Exception as e:
            print(f"Error saving model: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass
