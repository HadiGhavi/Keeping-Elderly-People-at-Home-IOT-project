
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from ClassificationAlgorithm.test_process import HealthStatePredictor
from Microservices.DataIngestion.mqttConnector  import MQTTService
from Microservices.DataIngestion.influxDbService import InfluxDBService
from Microservices.DataIngestion.config import Config

import time
import json
import cherrypy
import requests
import threading
import webbrowser

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
        try:
            self.predict = HealthStatePredictor(Config.CLASSIFICATION["TRAINMODEL"])
        except (FileNotFoundError, ImportError) as e:
            print(f"Warning: Could not load ML model: {e}")
            print("Using mock predictor for testing")
            self.predict = MockPredictor()
        self.influx = InfluxDBService("iot_health")
        
        # ✅ Start MQTT automatically
        print("Starting MQTT subscriber...")
        background_thread = threading.Thread(target=self.main, daemon=True)
        background_thread.start()
    
    @cherrypy.expose
    def index(self):
        # ✅ Remove MQTT startup from here
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return json.dumps({
            "message": "data handler API - MQTT subscriber running",
            "endpoints": {"GET /getUserData/<id>": "get user data from db"}
        }).encode('utf-8')
    
    @cherrypy.expose
    def getUserData(self,user_id):
        data=self.influx.getUserData(user_id)
        results = []
        for table in data:
         for record in table.records:
            results.append({
                "time": str(record.get_time()),
                "measurement": record.get_measurement(),
                "field": record.get_field(),
                "value": record.get_value(),
                "user_id":record["UserId"],
                "full_name":record["full_name"]
            })

        # Now you can serialize to JSON
        json_data = json.dumps(results)
        return json.dumps(json_data).encode('utf-8')
   

    def process(self, topic: str, message):
        """Process incoming MQTT messages"""
        try:
            json_message = json.loads(message)
            measurement = topic.split("/")[-1]
            
            print(f"Processing {measurement}: {json_message}")
            
            #user_sensitive = json_message["SensitiveSituation"]

            # Find available sensors
            available_sensors = {sensor["name"]: sensor for sensor in json_message["sensors"]}
            
            # Extract sensor values with flexible matching
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
                temp_value = 36.5  # Normal body temperature
                
            if oxygen_value is None:
                print("INFO: No oxygen sensor configured for this user")
                oxygen_value = 98.0  # Normal oxygen saturation
                
            if heart_rate_value is None:
                print("INFO: No heart rate sensor configured for this user") 
                heart_rate_value = 75  # Normal heart rate

            print(f"Final values - temp: {temp_value} (float), oxygen: {oxygen_value} (float), heart_rate: {heart_rate_value} (int)")
            
            # Predict health state
            predicted_state = self.predict.predict_state(temp_value, heart_rate_value, oxygen_value)
            print(f"Predicted state: {predicted_state}")
            
            res_obj = {
                "user_id": json_message["user_id"],
                "user_name": json_message["user_name"],
                "state": predicted_state,
                "temp": temp_value,
                "oxygen": oxygen_value,
                "heartRate": heart_rate_value
            }

            # Send notification if state matches user's sensitive situations
            if predicted_state in ["risky", "dangerous"]:
                print("Condition met - sending notification")
                try:
                    notif_services = requests.get("http://catalog:5001/services/notification")
                    json_notif = notif_services.json()
                    print(f"Notification service info: {json_notif}")
                    
                    print(f"Sending notification to: {json_notif['url']}:{json_notif['port']}/sendNotif")
                    print(f"Notification payload: {res_obj}")
                    
                    response = requests.post(
                        f"{json_notif['url']}:{json_notif['port']}/sendNotif",
                        json=res_obj,
                        timeout=10
                    )
                    
                    print(f"Notification response status: {response.status_code}")
                    print(f"Notification response text: {response.text}")
                    
                    if response.status_code != 200:
                        print(f"Notification failed with status {response.status_code}")
                    else:
                        print("Notification sent successfully")
                        
                except Exception as e:
                    print(f"Exception sending notification: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"No notification - predicted state '{predicted_state}' not in ['risky', 'dangerous']")

            # Store in InfluxDB
            influx_success, influx_msg = self.influx.writeInflux(measurement, res_obj)
            print("Influx write message:" + influx_msg)
            return influx_success
            
        except ValueError:
            print(f"Invalid message format: {message}")
            return False
        except Exception as e:
            print(f"Processing error: {e}")
            return False

    def main(self):
        mqtt_service=requests.get("http://catalog:5001/services/mqtt")
        json_mqtt=mqtt_service.json()

        mqtt_subscriber = MQTTService(
            host=json_mqtt["url"],
            port=json_mqtt["port"],
            auth=None
        )
        
        mqtt_subscriber.subscribe(
            topics=json_mqtt["topics"],
            message_handler=self.process
        )
        
        try:
            while True:
                time.sleep(30)
        except KeyboardInterrupt:
            print("Shutting down...")
            mqtt_subscriber.disconnect()

if __name__ == "__main__":
    response = requests.post(
        f"http://catalog:5001/services/",
        json={
            "dataIngestion": {
            "url": "http://data_ingestion",
            "port": 2500,
            "endpoints": {
                "GET /getUserData/<id>": "get user data from db"
            }
        }
        }
    )
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
