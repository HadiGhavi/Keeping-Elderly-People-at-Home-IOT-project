import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
import json
from influxdb_client import InfluxDBClient, Point, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
import certifi
from adapterInterface import TimeSeriesAdapter

# Set SSL certificates
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

class InfluxDBAdapter(TimeSeriesAdapter):
    """ InfluxDB implementation of the TimeSeriesAdapter interface """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize InfluxDB adapter with configuration.
        
        Args:
            config: Dictionary containing:
                - host: InfluxDB host URL
                - token: Authentication token
                - org: Organization name
                - bucket: Bucket/database name
        """
        self.config = config
        self.host = config.get('host')
        self.token = config.get('token')
        self.org = config.get('org')
        self.bucket = config.get('bucket')
        self.client = None
        self.write_api = None
        self.query_api = None
        
    def connect(self) -> bool:
        """Establish connection to InfluxDB"""
        try:
            print(f"InfluxDB: Attempting connection to {self.host}")
            
            self.client = InfluxDBClient(
                url=self.host,
                token=self.token,
                org=self.org,
                ssl_ca_cert=certifi.where()
            )
            
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.query_api = self.client.query_api()
            
            print("InfluxDB: Testing connection with a simple query...")
            
            # Test with a simple query instead of health check
            try:
                test_query = f'''
                from(bucket: "{self.bucket}")
                |> range(start: -1m)
                |> limit(n: 1)
                '''
                result = self.query_api.query(test_query)
                print("InfluxDB: Query test successful - connection established")
                return True
                
            except Exception as query_error:
                print(f"InfluxDB: Query test failed: {query_error}")
                # If query fails due to bucket access but client is OK, still consider it connected
                if "unauthorized" in str(query_error).lower():
                    print("InfluxDB: Authentication issue - check token permissions")
                    return False
                elif "bucket" in str(query_error).lower():
                    print("InfluxDB: Bucket issue but connection seems OK")
                    return True
                else:
                    print("InfluxDB: Connection test failed")
                    return False
            
        except Exception as e:
            print(f"InfluxDB connection failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def disconnect(self) -> bool:
        """Close InfluxDB connection"""
        try:
            if self.client:
                self.client.close()
            return True
        except Exception as e:
            print(f"InfluxDB disconnect failed: {e}")
            return False
    
    def write_data(self, measurement: str, data: Dict[str, Any]) -> tuple[bool, str]:
        """
        Write data to InfluxDB.
        
        Expected data format:
        {
            "tags": {"user_id": "123", "sensor_type": "temp"},
            "fields": {"value": 36.5, "status": "normal"},
            "timestamp": datetime.now()  # Optional
        }
        """
        try:
            if not self.write_api:
                return False, "No connection to InfluxDB"
            
            # Extract components
            tags = data.get('tags', {})
            fields = data.get('fields', {})
            timestamp = data.get('timestamp', datetime.now())
            
            # Create InfluxDB point
            point = Point(measurement)
            
            # Add tags (indexed fields)
            for tag_key, tag_value in tags.items():
                point = point.tag(tag_key, str(tag_value))
            
            # Add fields (data values)
            for field_key, field_value in fields.items():
                point = point.field(field_key, field_value)
            
            # Set timestamp
            if timestamp:
                point = point.time(timestamp)
            
            # Write to InfluxDB
            self.write_api.write(bucket=self.bucket, record=point)
            
            return True, "Data written successfully"
            
        except InfluxDBError as e:
            return False, f"InfluxDB write error: {e}"
        except Exception as e:
            return False, f"Write error: {e}"
    
    def _serialize_datetime_objects(self, data):
        """Convert datetime objects to ISO strings for JSON serialization"""
        if isinstance(data, dict):
            return {key: self._serialize_datetime_objects(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._serialize_datetime_objects(item) for item in data]
        elif isinstance(data, datetime):
            return data.isoformat()
        else:
            return data
    
    def query_data(self, 
               measurement: str, 
               filters: Optional[Dict[str, Any]] = None,
               time_range: Optional[Dict[str, datetime]] = None,
               fields: Optional[List[str]] = None) -> tuple[bool, Union[List[Dict], str]]:
        """Query data from InfluxDB using Flux query language"""
        try:
            if not self.query_api:
                return False, "No connection to InfluxDB"
            
            # Build Flux query
            query_parts = [
                f'from(bucket: "{self.bucket}")',
            ]
            
            # Add time range - FIX THE TIME FORMATTING
            if time_range and 'start' in time_range:
                # Format datetime for Flux query - use RFC3339 format with quotes
                start_time = time_range['start'].strftime('%Y-%m-%dT%H:%M:%SZ')
                if 'end' in time_range:
                    end_time = time_range['end'].strftime('%Y-%m-%dT%H:%M:%SZ')
                    query_parts.append(f'|> range(start: {start_time}, stop: {end_time})')
                else:
                    query_parts.append(f'|> range(start: {start_time})')
            else:
                query_parts.append('|> range(start: -24h)')  # Default to last 24h
            
            # Add measurement filter
            query_parts.append(f'|> filter(fn: (r) => r._measurement == "{measurement}")')
            
            # Add custom filters
            if filters:
                for key, value in filters.items():
                    if isinstance(value, str):
                        query_parts.append(f'|> filter(fn: (r) => r.{key} == "{value}")')
                    else:
                        query_parts.append(f'|> filter(fn: (r) => r.{key} == {value})')
            
            # Add field filters
            if fields:
                field_filter = ' or '.join([f'r._field == "{field}"' for field in fields])
                query_parts.append(f'|> filter(fn: (r) => {field_filter})')
            
            flux_query = '\n'.join(query_parts)
            
            # Execute query
            result = self.query_api.query(flux_query)
            
            # Convert to standard format
            data = []
            for table in result:
                for record in table.records:
                    data.append({
                        "time": record.get_time(),  # Keep as datetime for now
                        "measurement": record.get_measurement(),
                        "field": record.get_field(),
                        "value": record.get_value(),
                        **{k: v for k, v in record.values.items()
                        if k not in ['_time', '_measurement', '_field', '_value']}
                    })

            # Serialize datetime objects before returning
            data = self._serialize_datetime_objects(data)
            return True, data
            
        except Exception as e:
            print(f"DEBUG: Query exception details: {e}")
            return False, f"Query error: {e}"
            
    def get_all_users(self) -> tuple[bool, Union[List[Dict], str]]:
        """Get all users who have data in the system"""
        try:
            if not self.query_api:
                return False, "No connection to InfluxDB"
            
            # Query to get unique users and their record counts
            flux_query = f'''
            from(bucket: "{self.bucket}")
            |> range(start: -30d)
            |> filter(fn: (r) => r._measurement == "value")
            |> group(columns: ["UserId", "full_name"])
            |> count()
            |> group()
            |> sort(columns: ["UserId"])
            '''
            
            result = self.query_api.query(flux_query)
            
            # Process results to get unique users
            users_dict = {}
            for table in result:
                for record in table.records:
                    user_id = record.values.get('UserId')
                    full_name = record.values.get('full_name', f'User {user_id}')
                    record_count = record.get_value()
                    
                    if user_id and user_id not in users_dict:
                        users_dict[user_id] = {
                            "user_id": user_id,
                            "full_name": full_name,
                            "record_count": record_count
                        }
            
            # Get last activity for each user
            for user_id, user_data in users_dict.items():
                last_activity_query = f'''
                from(bucket: "{self.bucket}")
                |> range(start: -30d)
                |> filter(fn: (r) => r._measurement == "value" and r.UserId == "{user_id}")
                |> last()
                '''
                
                try:
                    activity_result = self.query_api.query(last_activity_query)
                    for table in activity_result:
                        for record in table.records:
                            user_data["last_activity"] = record.get_time().isoformat()
                            break
                except:
                    user_data["last_activity"] = None
            
            users_list = list(users_dict.values())
            users_list = self._serialize_datetime_objects(users_list)
            
            return True, users_list
            
        except Exception as e:
            return False, f"Error getting users: {e}"
    
    def get_user_data(self, user_id: str,
                  time_range: Optional[Dict[str, datetime]] = None) -> tuple[bool, Union[List[Dict], str]]:
        """Get all sensor data for a specific user"""
        
        filters = {"UserId": user_id}
        success, data = self.query_data("value", filters=filters, time_range=time_range)
                
        if success and isinstance(data, list):
            # Ensure all datetime objects are serialized
            data = self._serialize_datetime_objects(data)
        
        return success, data
    
    def delete_user_data(self, user_id: str) -> tuple[bool, str]: 
        #Delete all data for a specific user
        try:
            if not self.client:
                return False, "No connection to InfluxDB"
            
            # InfluxDB delete API requires specific time range and predicate
            delete_api = self.client.delete_api()
            
            # Delete all data for user (last 10 years to cover all data)
            start = datetime.now() - timedelta(days=3650)
            stop = datetime.now()
            
            delete_api.delete(
                start=start,
                stop=stop,
                predicate=f'UserId="{user_id}"',
                bucket=self.bucket
            )
            
            return True, f"All data for user {user_id} deleted"
            
        except Exception as e:
            return False, f"Delete error: {e}" 
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get InfluxDB connection and status information"""
        try:
            info = {
                "adapter_type": "InfluxDB",
                "host": self.host,
                "org": self.org,
                "bucket": self.bucket,
                "connected": self.client is not None
            }
            
            if self.client:
                health = self.client.health()
                info["status"] = health.status
                info["version"] = getattr(health, 'version', 'unknown')
            
            return info
            
        except Exception as e:
            return {
                "adapter_type": "InfluxDB",
                "error": str(e),
                "connected": False
            }