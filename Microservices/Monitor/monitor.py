import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from Microservices.Monitor.sensor_generator import GenerateSensor
from Microservices.Monitor.mqttConnector import MQTTService
import time
import cherrypy
import requests
import json
import threading

class Monitor:
    def __init__(self):
        self.sensor = GenerateSensor()

    @cherrypy.expose
    def index(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return json.dumps({
            "message": "Sensor API",
            "endpoints": {
                "GET /read/<id>": "read sensor value from device",
            }
        }).encode('utf-8')
    
    @cherrypy.expose
    def read(self,chat_id):
       catalog_services=requests.get("http://catalog:5001/services/catalog")
       json_catalog=catalog_services.json()

       user_info=requests.get(json_catalog["url"]+":" + str(json_catalog["port"])+"/users/"+ chat_id)
       background_thread = threading.Thread(target= self.run,args=(user_info.json(),), daemon=True)
       background_thread.start()
      
       cherrypy.response.headers['Content-Type'] = 'application/json'
       
       return json.dumps({
            "message": "RUNNING SENSORS",
        }).encode('utf-8')
    
    def run(self,user_info):
        try:
            while True:
                publish_data={"user_id":user_info["user_chat_id"],"SensitiveSituation":user_info["SensitiveSituation"],"user_name":user_info["full_name"],"sensors":[]}
               
                for sensor in user_info["sensors"]:
                   sensor_value = self.sensor.read_value(int(sensor["min_level_alert"]),int(sensor["max_level_alert"]))
                   publish_data["sensors"].append({
                    "id": sensor["id"],
                    "name": sensor['name'],
                    "value":sensor_value
                   })
               
                if(len(publish_data["sensors"])==0):
                    continue
                self.read_and_publish(publish_data)
                time.sleep(60)
       
        except KeyboardInterrupt:
            print("Program stopped by user")
        finally:
            print("Monitoring stopped")
    
    def read_and_publish(self,data):
        if data is not None:
            mqtt_service=requests.get("http://catalog:5001/services/mqtt")
            json_mqtt=mqtt_service.json()
            print(json_mqtt)
            mqtt = MQTTService(
                host=json_mqtt["url"],
                port=json_mqtt["port"],
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
    response = requests.post(
        f"http://catalog:5001/services/",
        json={
            "sensor": {
            "url": "http://monitor:3500/read/",
            "port": 3500,
            "endpoints": {
                "GET /read/<id>": "read sensor value from device"
              }
            }
        }
    )
    
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 3500,
        'tools.encode.on': True,
        'tools.encode.encoding': 'utf-8'
    })
        
    cherrypy.quickstart(Monitor(), '/')