import os
import certifi
from Microservices.Common.config import Config
from datetime import datetime
from influxdb_client import InfluxDBClient, Point
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


    def get_user_health_data(self, user_id, hours=None, aggregate=False):
        try:
            clean_hours = int(str(hours).replace('h', '')) if hours else 24
            range_start = f"-{clean_hours}h"

            # Dynamic window calculation based on timeframe
            if clean_hours <= 24:
                window = "5m"
            elif clean_hours <= 48:
                window = "15m"
            elif clean_hours <= 72:
                window = "30m"
            else:
                window = "2h"
            
            if not aggregate:
                # Just filter and pivot
                query = f'''
                from(bucket: "{self.bucket}")
                |> range(start: {range_start})
                |> filter(fn: (r) => r._measurement == "value" and r.UserId == "{user_id}")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                '''
            else:
                # 1. Separate numeric and string data
                # 2. Aggregate them while they still have the _value column
                # 3. Pivot at end to join them into one row
                query = f'''
                data = from(bucket: "{self.bucket}")
                    |> range(start: {range_start})
                    |> filter(fn: (r) => r._measurement == "value" and r.UserId == "{user_id}")

                vitals = data
                    |> filter(fn: (r) => r._field != "state")
                    |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)

                status = data
                    |> filter(fn: (r) => r._field == "state")
                    |> aggregateWindow(every: {window}, fn: mode, createEmpty: false)

                union(tables: [vitals, status])
                    |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                '''
            
            result = self.query_api.query(query)
            data = []
            
            for table in result:
                for record in table.records:
                    v = record.values
                    data.append({
                        "time": record.get_time().isoformat(),
                        "temp": v.get("temp"),
                        "heart_rate": v.get("heart_rate"),
                        "oxygen": v.get("oxygen"),
                        "state": v.get("state") or "unknown"
                    })
            
            return True, data

        except Exception as e:
            print(f"Database Query Error: {str(e)}")
            return False, str(e)