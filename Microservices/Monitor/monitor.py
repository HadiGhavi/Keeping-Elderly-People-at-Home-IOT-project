import threading
import time
import requests
import json
from datetime import datetime
from Microservices.Monitor.sensor_generator import GenerateSensor
from Microservices.Monitor.MyMQTT import MyMQTT 
from Microservices.Common.config import Config
from Microservices.Common.utils import ServiceRegistry

class MonitorAdapter:
    def __init__(self):
        self.catalog_url = Config.SERVICES["catalog_url"]
        self.registry = ServiceRegistry()
        self.mqtt_info = self.registry.get_service_info("mqtt")
        self.sensor = GenerateSensor()
        
        self.device_threads = {}  # device_id -> thread
        self.device_stop_events = {}  # device_id -> stop_event
        self.user_devices = {}  # user_id -> [device_ids]
        self.lock = threading.Lock()
        self.last_check_time = datetime.now()

    def start_monitoring(self, chat_id):
        user_id = int(chat_id)
        user_response = requests.get(f"{self.catalog_url}/users/{chat_id}", timeout=5)
        if user_response.status_code != 200:
            return False, "User not found"
        
        user_info = user_response.json()
        user_device_ids = user_info.get("devices", [])
        
        started_devices = []
        already_running = []
        
        with self.lock:
            for device_id in user_device_ids:
                if device_id in self.device_threads and self.device_threads[device_id].is_alive():
                    already_running.append(device_id)
                    continue
                
                device_res = requests.get(f"{self.catalog_url}/devices/{device_id}")
                if device_res.status_code == 200:
                    device = device_res.json()
                    stop_event = threading.Event()
                    self.device_stop_events[device_id] = stop_event
                    
                    thread = threading.Thread(
                        target=self.run_device_loop,
                        args=(device, user_info, stop_event),
                        daemon=True
                    )
                    thread.start()
                    self.device_threads[device_id] = thread
                    started_devices.append(device_id)
            
            self.user_devices[user_id] = user_device_ids
        return True, {"started": started_devices, "already_running": already_running}

    def stop_monitoring(self, chat_id):
        user_id = int(chat_id)
        with self.lock:
            device_ids = self.user_devices.get(user_id, [])
            stopped = []
            for d_id in device_ids:
                if d_id in self.device_stop_events:
                    self.device_stop_events[d_id].set()
                    stopped.append(d_id)
            if user_id in self.user_devices:
                del self.user_devices[user_id]
            return True, stopped

    def run_device_loop(self, device, user_info, stop_event):
        device_id = device['id']
        
        # 'None' as notifier since this is a publisher only
        mqtt_client = MyMQTT(
            clientID=f"Monitor_{device_id}", 
            broker=self.mqtt_info["url"], 
            port=self.mqtt_info["port"], 
            notifier=None 
        )
        
        mqtt_client.start() 
        
        try:
            while not stop_event.is_set():
                self.last_check_time = datetime.now()
                val = self.sensor.read_value(0, 100, device['type'])
                if val is not None:
                    payload = {
                        "user_id": user_info['user_chat_id'],
                        "user_name": user_info['full_name'],
                        "sensors": [{"id": device_id, "name": device['type'], "value": val}]
                    }
                    mqtt_client.myPublish("iot_user_sensor/value", json.dumps(payload))
                time.sleep(30)
        finally:
            mqtt_client.stop()
            with self.lock:
                self.device_threads.pop(device_id, None)
                self.device_stop_events.pop(device_id, None)