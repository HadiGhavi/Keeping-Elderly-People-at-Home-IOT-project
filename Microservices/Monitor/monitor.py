import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from Microservices.Monitor.sensor_generator import GenerateSensor
from Microservices.Monitor.mqttConnector import MQTTService
from Microservices.Common.utils import ServiceRegistry,register_service_with_catalog
from Microservices.Common.config import Config
import time
import cherrypy
import requests
import json
import threading


class Monitor:
    def __init__(self):
        self.catalog_url = Config.SERVICES["catalog_url"]
        self.registry = ServiceRegistry()
        self.mqtt_info = self.registry.get_service_info("mqtt")
        self.sensor = GenerateSensor()
        
        # Track device threads (one thread per device)
        self.device_threads = {}  # device_id -> thread
        self.device_stop_events = {}  # device_id -> stop_event
        
        # Track which devices belong to which user
        self.user_devices = {}  # user_id -> [device_ids]
        
        # Thread lock for concurrent access
        self.lock = threading.Lock()

    @cherrypy.expose
    def index(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return json.dumps({
            "message": "Sensor API",
            "endpoints": {
                "GET /read/<id>": "read sensor value from device",
                "GET /stop/<id>": "stop sensor monitoring for user"
            }
        }).encode('utf-8')
    
    
    @cherrypy.expose
    def read(self, chat_id):
        try:
            user_id = int(chat_id)
            
            # Get user info from catalog
            user_response = requests.get(f"{self.catalog_url}/users/{chat_id}", timeout=5)
            
            if user_response.status_code != 200:
                return json.dumps({
                    "error": "User not found"
                }).encode('utf-8')
            
            user_info = user_response.json()
            user_device_ids = user_info.get("devices", [])
            
            if not user_device_ids:
                return json.dumps({
                    "error": "User has no devices registered"
                }).encode('utf-8')
            
            # Fetch device details from catalog
            devices_data = []
            for device_id in user_device_ids:
                try:
                    device_response = requests.get(
                        f"{self.catalog_url}/devices/{device_id}",
                        timeout=5
                    )
                    if device_response.status_code == 200:
                        devices_data.append(device_response.json())
                except Exception as e:
                    print(f"Error fetching device {device_id}: {e}")
            
            if not devices_data:
                return json.dumps({
                    "error": "Could not fetch device information"
                }).encode('utf-8')
            
            # Start a separate thread for each device
            started_devices = []
            already_running = []
            
            with self.lock:
                for device in devices_data:
                    device_id = device['id']
                    
                    # Check if device thread is already running
                    if device_id in self.device_threads and self.device_threads[device_id].is_alive():
                        already_running.append(device_id)
                        continue
                    
                    # Create stop event for this device
                    self.device_stop_events[device_id] = threading.Event()
                    
                    # Start device monitoring thread
                    device_thread = threading.Thread(
                        target=self.run_device,
                        args=(device, user_info),
                        daemon=True
                    )
                    device_thread.start()
                    
                    # Track the thread
                    self.device_threads[device_id] = device_thread
                    started_devices.append(device_id)
                
                # Track user's devices
                self.user_devices[user_id] = user_device_ids
            
            message = f"Started monitoring {len(started_devices)} device(s)"
            if already_running:
                message += f". {len(already_running)} device(s) already running"
            
            return json.dumps({
                "message": message,
                "started": started_devices,
                "already_running": already_running
            }).encode('utf-8')
            
        except Exception as e:
            print(f"Error in read endpoint: {e}")
            return json.dumps({
                "error": f"Failed to start monitoring: {str(e)}"
            }).encode('utf-8')

    
    @cherrypy.expose
    def stop(self, chat_id):
        cherrypy.response.headers['Content-Type'] = 'application/json'

        try:
            user_id = int(chat_id)
            
            with self.lock:
                # Get all devices for this user
                device_ids = self.user_devices.get(user_id, [])
                
                if not device_ids:
                    return json.dumps({
                        "message": f"No active monitoring found for user {user_id}"
                    }).encode('utf-8')
                
                # Stop all device threads for this user
                stopped_devices = []
                for device_id in device_ids:
                    if device_id in self.device_stop_events:
                        self.device_stop_events[device_id].set()
                        stopped_devices.append(device_id)
                
                # Remove user tracking
                if user_id in self.user_devices:
                    del self.user_devices[user_id]
                
                return json.dumps({
                    "message": f"Stop signal sent to {len(stopped_devices)} device(s)",
                    "stopped_devices": stopped_devices
                }).encode('utf-8')
                
        except Exception as e:
            print(f"Error in stop endpoint: {e}")
            return json.dumps({
                "error": f"Failed to stop monitoring: {str(e)}"
            }).encode('utf-8')

    def run_device(self, device, user_info):
        """
        Run a single device as an independent MQTT client.
        Each device has its own thread and MQTT connection.
        """
        device_id = device['id']
        device_type = device['type']
        user_id = user_info['user_chat_id']
        user_name = user_info['full_name']
        
        mqtt_client = None
        
        try:
            # Create dedicated MQTT client for this device
            mqtt_client = MQTTService(
                host=self.mqtt_info["url"],
                port=self.mqtt_info["port"],
                auth=None
            )
            print(f"Device {device_id} ({device_type}) - MQTT client connected")
            
            while True:
                # Check if stop was requested
                if device_id in self.device_stop_events and self.device_stop_events[device_id].is_set():
                    print(f"Stopping device {device_id}")
                    break
                
                try:
                    # Generate sensor value based on device type
                    sensor_value = self.sensor.read_value(
                        min_value=0,
                        max_value=100,
                        sensor_name=device_type
                    )
                    
                    if sensor_value is not None:
                        # Prepare data for this specific device
                        publish_data = {
                            "user_id": user_id,
                            "user_name": user_name,
                            "sensors": [{
                                "id": device_id,
                                "name": device_type,
                                "value": sensor_value
                            }]
                        }
                        
                        # Publish data
                        print(f"Device {device_id} ({device_type}) - Publishing value: {sensor_value}")
                        success = mqtt_client.publish(
                            "iot_user_sensor/value",
                            payload=json.dumps(publish_data),
                            retain=False
                        )
                        
                        if success:
                            # Update device timestamp in catalog
                            try:
                                requests.put(
                                    f"{self.catalog_url}/devices/{device_id}",
                                    json={"last_update": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                                    timeout=3
                                )
                            except Exception as update_error:
                                print(f"Device {device_id} - Could not update timestamp: {update_error}")
                        else:
                            print(f"Device {device_id} - Failed to publish")
                    else:
                        print(f"Device {device_id} - Generated None value, skipping")
                
                except Exception as e:
                    print(f"Device {device_id} - Error generating/publishing value: {e}")
                
                # Wait before next reading (30 seconds)
                time.sleep(30)
                
        except KeyboardInterrupt:
            print(f"Device {device_id} - Stopped by user")
        except Exception as e:
            print(f"Device {device_id} - Error in monitoring loop: {e}")
        finally:
            # Clean up MQTT connection
            if mqtt_client:
                try:
                    mqtt_client.disconnect()
                    print(f"Device {device_id} - MQTT client disconnected")
                except Exception as e:
                    print(f"Device {device_id} - Error disconnecting MQTT: {e}")
            
            # Clean up thread tracking
            with self.lock:
                if device_id in self.device_stop_events:
                    del self.device_stop_events[device_id]
                if device_id in self.device_threads:
                    del self.device_threads[device_id]
            
            print(f"Device {device_id} - Monitoring stopped")


if __name__ == "__main__":

    register_service_with_catalog(service_name="sensor",
                                  url="http://monitor",
                                  port=3500,
                                  endpoints={
                                      "GET /read/<id>": "read sensor value from device",
                                      "GET /stop/<id>": "stop sensor monitoring for user"
                                  })
    
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 3500,
        'tools.encode.on': True,
        'tools.encode.encoding': 'utf-8'
    })
        
    cherrypy.quickstart(Monitor(), '/')