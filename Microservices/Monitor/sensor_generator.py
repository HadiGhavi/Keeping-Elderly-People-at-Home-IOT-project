import random
import time

class GenerateSensor:
   
    def read_value(self,min_value,max_value):
        return round(random.uniform(min_value, max_value), 1)
    
    # For real sensor implementation:
    # def __init__(self, pin):
    #     import adafruit_dht
    #     self.sensor = adafruit_dht.DHT22(pin)
    # 
    # def read_temperature(self):
    #     try:
    #         return self.sensor.temperature
    #     except RuntimeError as e:
    #         print(f"Sensor read error: {e}")
    #         return None
    #     finally:
    #         self.sensor.exit()
