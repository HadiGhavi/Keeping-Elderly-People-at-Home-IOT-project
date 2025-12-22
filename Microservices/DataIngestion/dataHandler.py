import time
import json
import threading
import requests
import os
import pickle
import numpy as np
from datetime import datetime
from Microservices.Common.config import Config
from Microservices.Common.utils import ServiceRegistry
from Microservices.DataIngestion.mqttConnector import MQTTService
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

    def _load_model(self):
        model_path = Config.CLASSIFICATION["TRAINMODEL"]
        if os.path.exists(model_path) and os.path.getsize(model_path) > 0:
            try: return HealthStatePredictor(model_path)
            except: return MockPredictor()
        return MockPredictor()

    def start_services(self):
        # Start MQTT Subscriber
        threading.Thread(target=self._mqtt_loop, daemon=True).start()
        # Start Retraining Loop
        threading.Thread(target=self._retrain_loop, daemon=True).start()

    def _mqtt_loop(self):
        mqtt_sub = MQTTService(host=self.mqtt_info["url"], port=self.mqtt_info["port"])
        mqtt_sub.subscribe(topics=self.mqtt_info["topics"], message_handler=self.process_mqtt_message)
        while True: time.sleep(30)

    def process_mqtt_message(self, topic, message):
        try:
            msg = json.loads(message)
            user_id = str(msg["user_id"])
            user_name = msg["user_name"]
            now = time.time()

            with self.cache_lock:
                if user_id not in self.user_sensor_cache: self.user_sensor_cache[user_id] = {}
                for s in msg["sensors"]:
                    self.user_sensor_cache[user_id][s["name"]] = {"value": s["value"], "timestamp": now}
                
                cache = self.user_sensor_cache[user_id]
                vals = {k: cache[k]["value"] for k in ["temp", "heart_rate", "oxygen"] 
                        if k in cache and (now - cache[k]["timestamp"]) <= self.cache_timeout}

            if len(vals) == 3:
                state = self.predict.predict_state(float(vals["temp"]), int(float(vals["heart_rate"])), float(vals["oxygen"]))
                self._write_to_db(user_id, user_name, vals["temp"], vals["heart_rate"], vals["oxygen"], state)
        except Exception as e: print(f"Processing error: {e}")

    def _write_to_db(self, uid, name, t, hr, ox, state):
        payload = {"user_id": uid, "user_name": name, "temp": t, "heart_rate": hr, "oxygen": ox, "state": state}
        requests.post(f"{self.database_service_url}/write", json=payload, timeout=5)

    def _retrain_loop(self):
        while True:
            time.sleep(self.retrain_interval)
            # Logic for _retrain_model goes here (omitted for brevity, keep your original logic)
            print("Checking for model retraining...")