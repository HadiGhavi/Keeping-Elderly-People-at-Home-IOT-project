import os
import json
import certifi
from Microservices.Common.config import Config
from datetime import datetime, timedelta
from influxdb_client import InfluxDBClient, Point, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS

# Set SSL certificates for InfluxDB connection
os.environ['SSL_CERT_FILE'] = certifi.where()

class InfluxDBAdapter():
    def __init__(self):
       
        self.host = Config.DATABASE['influxdb']['host']
        self.token = Config.DATABASE['influxdb']['token']
        self.org = Config.DATABASE['influxdb']['org']   
        self.bucket = Config.DATABASE['influxdb']['bucket']

        self.client = InfluxDBClient(
            url=self.host,
            token=self.token,
            org=self.org,
            ssl_ca_cert=certifi.where()
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()

    def write_health_data(self, user_id, user_name, temp, heart_rate, oxygen, state):
        try:
            point = Point("value") \
                .tag("UserId", str(user_id)) \
                .tag("full_name", user_name) \
                .field("temp", float(temp)) \
                .field("heart_rate", int(heart_rate)) \
                .field("oxygen", float(oxygen)) \
                .field("state", state) \
                .time(datetime.utcnow())
            
            self.write_api.write(bucket=self.bucket, record=point)
            return True, "Data written successfully"
        except Exception as e:
            return False, str(e)

    def get_user_health_data(self, user_id, hours=None):
        try:
            range_start = f"-{hours}h" if hours else "-24h"
            query = f'''
            from(bucket: "{self.bucket}")
            |> range(start: {range_start})
            |> filter(fn: (r) => r._measurement == "value")
            |> filter(fn: (r) => r.UserId == "{user_id}")
            '''
            result = self.query_api.query(query)
            data = []
            for table in result:
                for record in table.records:
                    data.append({
                        "time": record.get_time().isoformat(),
                        "field": record.get_field(),
                        "value": record.get_value()
                    })
            return True, data
        except Exception as e:
            return False, str(e)