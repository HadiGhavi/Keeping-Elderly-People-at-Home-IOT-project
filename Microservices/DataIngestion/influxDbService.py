from influxdb_client import InfluxDBClient, Point
from datetime import datetime, timedelta
import pandas as pd
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
import os
import certifi

# Set SSL certificates
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

class InfluxDBService:
    def __init__(self, database="iot_keep_elderly_peaple"): 
        self.token = "t15TuVCslGA7G4w8zPVoLg-EKyE6wr2I69ANHNxDJgSkJdb241st6xifml8LF5L0ddjIYQDzl8iV22xZCAN8Kg=="
        self.org = "University"  
        self.host = "https://us-east-1-1.aws.cloud2.influxdata.com"  
        
        self.influxDBclient = InfluxDBClient(
            url=self.host, 
            token=self.token, 
            org=self.org, 
            database=database,
            ssl_ca_cert=certifi.where()
        )
        self.database = database

    def getUserData(self, client_id):
        try:
            flux_query = f"""
            from(bucket: "{self.database}")
            |> range(start: -1h)
            |> filter(fn: (r) =>
                r._measurement == "value" and
                r.UserId == "{client_id}" and
                (r._field == "heart_rate" or
                 r._field == "oxygen" or
                 r._field == "state" or
                 r._field == "temp")
            )
            """
            
            query_api = self.influxDBclient.query_api()
            result = query_api.query(flux_query)
            print(result)
            return result
            
        except InfluxDBError as e:
            print(f"Error querying InfluxDB: {e}")
            return None

    def writeInflux(self, measurement, sensor_info):
        print("starting write")
        try:
            write_api = self.influxDBclient.write_api(write_options=SYNCHRONOUS)
            
            data = [
                {
                    "measurement": measurement,
                    "tags": {
                        "UserId": sensor_info["user_id"],
                        "full_name": sensor_info["user_name"]
                    },
                    "fields": {
                        "temp": sensor_info["temp"],
                        "heart_rate": sensor_info["heartRate"],
                        "oxygen": sensor_info["oxygen"],
                        "state": sensor_info["state"],
                    },
                }
            ]
            
            write_api.write(bucket=self.database, record=data)
            print("Data written successfully!")
            # ✅ Return success tuple
            return True, "Data written successfully!"
            
        except Exception as e:
            error_msg = f"InfluxDB write failed: {e}"
            print(error_msg)
            
            # ✅ Return failure tuple
            return False, error_msg

if __name__ == "__main__":
    # Test with your working credentials
    db = InfluxDBService("iot_keep_elderly_people")  # Use your existing bucket
    