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
        self.active_monitors = {}  # Track active monitoring threads
        self.stop_events = {}      # Track stop events for each user

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
            
            # Check if already monitoring this user
            if user_id in self.active_monitors and self.active_monitors[user_id].is_alive():
                return json.dumps({
                    "message": f"Already monitoring user {user_id}"
                }).encode('utf-8')
            
            # Get user info from catalog
            user_info = requests.get(self.catalog_url + "/users/" + chat_id)
            
            # Create stop event for this user
            self.stop_events[user_id] = threading.Event()
            
            # Start monitoring thread
            background_thread = threading.Thread(
                target=self.run, 
                args=(user_info.json(), user_id), 
                daemon=True
            )
            background_thread.start()
            
            # Track the thread
            self.active_monitors[user_id] = background_thread
            
            return json.dumps({
                "message": "RUNNING SENSORS"
            }).encode('utf-8')
            
        except Exception as e:
            return json.dumps({
                "error": f"Failed to start monitoring: {str(e)}"
            }).encode('utf-8')

    
    @cherrypy.expose
    def stop(self, chat_id):
        cherrypy.response.headers['Content-Type'] = 'application/json'

        #print(f"DEBUG: Stop request received for user {chat_id}")
        #print(f"DEBUG: Active monitors: {list(self.active_monitors.keys())}")
        #print(f"DEBUG: Stop events: {list(self.stop_events.keys())}")

        try:
            user_id = int(chat_id)
            if user_id in self.stop_events:
                # Signal the monitoring thread to stop
                self.stop_events[user_id].set()
                #print(f"DEBUG: Set stop event for user {user_id}")
                
                # DON'T delete the stop event here - let the monitoring thread clean up
                # The monitoring thread will clean up when it sees the stop flag
                
                return json.dumps({
                    "message": f"Stop signal sent to user {user_id}"
                }).encode('utf-8')
            else:
                return json.dumps({
                    "message": f"No active monitoring found for user {user_id}"
                }).encode('utf-8')
                
        except Exception as e:
            return json.dumps({
                "error": f"Failed to stop monitoring: {str(e)}"
            }).encode('utf-8')

    def run(self, user_info, user_id):
        try:
            while True:
                # Check if stop was requested
                if user_id in self.stop_events and self.stop_events[user_id].is_set():
                    print(f"Stopping monitoring for user {user_id}")
                    break

                #print(f"User info received: {user_info}")  # Debug line
                #print(f"Number of sensors configured: {len(user_info['sensors'])}")  # Debug line
                
                publish_data = {
                    "user_id": user_info["user_chat_id"],
                    "user_name": user_info["full_name"],
                    "sensors": []
                }
            
                for i, sensor in enumerate(user_info["sensors"]):
                    print(f"Processing sensor {i+1}: {sensor}")  # Debug line
                    try:
                        # The new generator automatically produces realistic values based on sensor name
                        sensor_value = self.sensor.read_value(
                        min_value=0,  # Dummy values - generator uses realistic ranges internally
                        max_value=100, 
                        sensor_name=sensor['name']  # Pass sensor name for intelligent detection
                        )
                        print(f"Generated value for {sensor['name']}: {sensor_value}")  # Debug line
                        
                        if sensor_value is not None:  # Add this check

                            publish_data["sensors"].append({
                                "id": sensor["id"],
                                "name": sensor['name'],
                                "value": sensor_value
                            })
                        else:
                            print(f"Sensor {sensor['name']} returned None value")
            
                    except Exception as e:
                        print(f"Error generating sensor value for {sensor['name']}: {e}")
                        continue
            
                print(f"Final publish_data: {publish_data}")  # Debug line
                
                if len(publish_data["sensors"]) == 0:
                    print("No sensor data generated, skipping publish")
                    continue
                    
                self.read_and_publish(publish_data)
                time.sleep(30)
                
        except KeyboardInterrupt:
            print("Program stopped by user")
        finally:
            # Clean up when the thread exits
            print(f"Monitoring stopped for user {user_id}")
            if user_id in self.stop_events:
                del self.stop_events[user_id]
            if user_id in self.active_monitors:
                del self.active_monitors[user_id]
    
    def read_and_publish(self,data):
        if data is not None:
            
            mqtt = MQTTService(
                host=self.mqtt_info["url"],
                port=self.mqtt_info["port"],
                auth=None
            )
            print(data)
            success = mqtt.publish(
                "iot_user_sensor/value",
                payload=json.dumps(data),
                retain=False
            )
            if success:
                print("Published successfully")
            else:
                print("Failed to publish")
        else:
            print("Failed to read temperature")

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