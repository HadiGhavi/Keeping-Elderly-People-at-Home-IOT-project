import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import requests
from databaseFactory import DatabaseService 
import cherrypy
import json
import pandas as pd
from datetime import datetime, timedelta
from config import Config

class DatabaseAdapterService:
    """ Main CherryPy web service that exposes REST endpoints """
    def __init__(self):
        self.database = DatabaseService(Config.DATABASE)

    @cherrypy.expose
    def index(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return json.dumps({
            "message": "Database Adapter Service",
            "version": "1.0",
            "database_info": self.database.get_database_info(),
            "endpoints": {
                "POST /write": "write health data to database",
                "GET /read/<user_id>": "get user health data", 
                "GET /aggregated/<user_id>": "get aggregated user health data for charts",
                "DELETE /delete/<user_id>": "delete user data",
                "GET /info": "get database adapter information",
                "POST /switch": "switch database adapter",
                "GET /adapters": "list available adapters"
            }
        }).encode('utf-8')
    
    @cherrypy.expose
    def write(self):
        """Write health data to database"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        if cherrypy.request.method != "POST":
            raise cherrypy.HTTPError(405, "Method Not Allowed")
        
        try:
            # Parse JSON request body
            data = json.loads(cherrypy.request.body.read().decode('utf-8'))
            
            # Validate required fields
            required_fields = ['user_id', 'user_name', 'temp', 'heart_rate', 'oxygen', 'state']
            if not all(field in data for field in required_fields):
                return json.dumps({
                    "success": False,
                    "message": f"Missing required fields: {required_fields}"
                }).encode('utf-8')
            
            # Write to database
            success, message = self.database.write_health_data(
                user_id=str(data['user_id']),
                user_name=data['user_name'],
                temp=float(data['temp']),
                heart_rate=int(data['heart_rate']),
                oxygen=float(data['oxygen']),
                state=data['state']
            )
            
            return json.dumps({
                "success": success,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }).encode('utf-8')
            
        except json.JSONDecodeError:
            return json.dumps({
                "success": False,
                "message": "Invalid JSON in request body"
            }).encode('utf-8')
        except Exception as e:
            return json.dumps({
                "success": False,
                "message": f"Error writing data: {str(e)}"
            }).encode('utf-8')
        
    @cherrypy.expose
    def users(self):
        """Get all users who have data in the system"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        try:
            success, data = self.database.get_all_users()
            
            return json.dumps({
                "success": success,
                "data": data if success else [],
                "count": len(data) if success and isinstance(data, list) else 0,
                "timestamp": datetime.now().isoformat()
            }).encode('utf-8')
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "message": f"Error getting users: {str(e)}",
                "data": []
            }).encode('utf-8')
        
    @cherrypy.expose
    def read(self, user_id, hours=None, start_time=None, end_time=None):
        """Get health data for a specific user with optional time filtering"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        try:
            # Build time range if provided
            time_range = None
            if hours:
                try:
                    hours_int = int(hours)
                    end_time_dt = datetime.now()
                    start_time_dt = end_time_dt - timedelta(hours=hours_int)
                    time_range = {"start": start_time_dt, "end": end_time_dt}
                    print(f"DEBUG: Time range created: {start_time_dt} to {end_time_dt}")
                except ValueError as e:
                    print(f"DEBUG: Hours parameter error: {e}")
                    return json.dumps({
                        "success": False,
                        "message": f"Invalid hours parameter: {hours}",
                        "data": []
                    }).encode('utf-8')
            
            print(f"DEBUG: Calling get_user_health_data with user_id={user_id}, time_range={time_range}")
            
            # Get filtered data from database
            success, data = self.database.get_user_health_data(user_id, time_range)
            
            print(f"DEBUG: Database response: success={success}, data_count={len(data) if isinstance(data, list) else 'N/A'}")
            
            return json.dumps({
                "success": success,
                "data": data if success else [],
                "user_id": user_id,
                "time_range": f"last {hours} hours" if hours else "all data",
                "timestamp": datetime.now().isoformat()
            }).encode('utf-8')
            
        except Exception as e:
            print(f"DEBUG: Exception in read method: {e}")
            import traceback
            traceback.print_exc()
            return json.dumps({
                "success": False,
                "message": f"Error reading data: {str(e)}",
                "data": []
            }).encode('utf-8')

    @cherrypy.expose
    def aggregated(self, user_id, hours=24):
        """Get aggregated health data for charts with time-based averaging and health state prioritization"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        try:
            # Build time range
            hours_int = int(hours)
            end_time_dt = datetime.now()
            start_time_dt = end_time_dt - timedelta(hours=hours_int)
            time_range = {"start": start_time_dt, "end": end_time_dt}
            
            #print(f"DEBUG: Getting aggregated data for user {user_id}, last {hours_int} hours")
            
            # Get raw data from database
            success, raw_data = self.database.get_user_health_data(user_id, time_range)
            
            if not success or not raw_data:
                return json.dumps({
                    "success": False,
                    "message": "No data found for aggregation",
                    "data": []
                }).encode('utf-8')
            
            # Convert to DataFrame for aggregation
            df = pd.DataFrame(raw_data)
            if df.empty:
                return json.dumps({
                    "success": False,
                    "message": "No data available for aggregation",
                    "data": []
                }).encode('utf-8')
            
            # Convert time column to datetime and set as index
            df['time'] = pd.to_datetime(df['time'])
            df = df.sort_values('time')
            
            print(f"DEBUG: Original data shape: {df.shape}")
            print(f"DEBUG: Unique fields: {df['field'].unique()}")
            
            # Separate numeric and categorical data
            numeric_fields = ['temp', 'heart_rate', 'oxygen']
            numeric_df = df[df['field'].isin(numeric_fields)].copy()
            categorical_df = df[df['field'] == 'state'].copy()
            
            # Determine aggregation frequency based on time period
            if hours_int <= 24:
                resample_freq = '5min'
                sample_info = "5-minute averages"
            elif hours_int <= 48:
                resample_freq = '15min'
                sample_info = "15-minute averages"
            elif hours_int <= 72:
                resample_freq = '30min'
                sample_info = "30-minute averages"
            else:
                resample_freq = '2H'
                sample_info = "2-hour averages"
            
            aggregated_data = []
            
            # Process numeric fields with averaging
            if not numeric_df.empty:
                # Convert values to numeric
                numeric_df['value'] = pd.to_numeric(numeric_df['value'], errors='coerce')
                numeric_df = numeric_df.dropna(subset=['value'])
                
                for field in numeric_fields:
                    field_data = numeric_df[numeric_df['field'] == field].copy()
                    if not field_data.empty:
                        field_data = field_data.set_index('time')
                        
                        try:
                            resampled = field_data['value'].resample(resample_freq).agg({
                                'mean': 'mean',
                                'min': 'min', 
                                'max': 'max',
                                'count': 'count'
                            }).dropna()
                            
                            for timestamp, row in resampled.iterrows():
                                if row['count'] > 0:
                                    aggregated_data.append({
                                        'time': timestamp.isoformat(),
                                        'field': field,
                                        'value': float(row['mean']),
                                        'min_value': float(row['min']),
                                        'max_value': float(row['max']),
                                        'sample_count': int(row['count'])
                                    })
                        except Exception as field_error:
                            print(f"Error processing field {field}: {field_error}")
                            continue
            
            # Process categorical data (health states) with weighted priority
            if not categorical_df.empty:
                categorical_df = categorical_df.set_index('time')
                
                # Define valid health states and weights
                VALID_STATES = {'normal': 1, 'risky': 2, 'dangerous': 3}
                STATE_WEIGHTS = {'dangerous': 3, 'risky': 2, 'normal': 1}
                
                def get_weighted_most_common_state(series):
                    """Get the most common state with weighted priority (dangerous > risky > normal)"""
                    if series.empty:
                        return None
                    
                    # Filter to only valid states
                    valid_series = series[series.isin(VALID_STATES.keys())]
                    if valid_series.empty:
                        return None
                    
                    # Count occurrences of each state
                    state_counts = valid_series.value_counts()
                    
                    # Calculate weighted scores for each state present
                    weighted_scores = {}
                    for state, count in state_counts.items():
                        if state in STATE_WEIGHTS:
                            weighted_scores[state] = count * STATE_WEIGHTS[state]
                    
                    if not weighted_scores:
                        return None
                    
                    # Return the state with the highest weighted score
                    best_state = max(weighted_scores.keys(), key=lambda state: weighted_scores[state])
                    
                    """ # Debug info when there are multiple states
                    if len(weighted_scores) > 1:
                        score_info = {state: f"{count}x{STATE_WEIGHTS[state]}={score}" 
                                    for state, score in weighted_scores.items() 
                                    for count in [state_counts[state]]}
                        print(f"Weighted scoring: {score_info} → chose '{best_state}'") """
                    
                    return best_state
                
                try:
                    # Find weighted most common state in each time window
                    resampled_states = categorical_df['value'].resample(resample_freq).apply(
                        get_weighted_most_common_state
                    ).dropna()
                    
                    for timestamp, state_value in resampled_states.items():
                        if state_value is not None and state_value in VALID_STATES:
                            aggregated_data.append({
                                'time': timestamp.isoformat(),
                                'field': 'state',
                                'value': str(state_value),
                                'min_value': str(state_value),
                                'max_value': str(state_value),
                                'sample_count': 1
                            })
                            
                except Exception as state_error:
                    print(f"Error processing health states: {state_error}")
            
            #print(f"DEBUG: Final aggregated data count: {len(aggregated_data)}")
            
            return json.dumps({
                "success": True,
                "data": aggregated_data,
                "user_id": user_id,
                "time_range": f"last {hours_int} hours",
                "sample_info": sample_info,
                "aggregation_frequency": resample_freq,
                "timestamp": datetime.now().isoformat()
            }).encode('utf-8')
            
        except Exception as e:
            print(f"DEBUG: Exception in aggregated method: {e}")
            import traceback
            traceback.print_exc()
            return json.dumps({
                "success": False,
                "message": f"Error aggregating data: {str(e)}",
                "data": []
            }).encode('utf-8')
    
    @cherrypy.expose
    def delete(self, user_id):
        """Delete all data for a specific user"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        if cherrypy.request.method != "DELETE":
            raise cherrypy.HTTPError(405, "Method Not Allowed")
        
        try:
            success, message = self.database.delete_user_data(user_id)
            
            return json.dumps({
                "success": success,
                "message": message,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }).encode('utf-8')
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "message": f"Error deleting data: {str(e)}"
            }).encode('utf-8')
    
    @cherrypy.expose
    def info(self):
        """Get database adapter information"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        try:
            db_info = self.database.get_database_info()
            return json.dumps({
                "success": True,
                "database_info": db_info,
                "timestamp": datetime.now().isoformat()
            }).encode('utf-8')
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "message": f"Error getting info: {str(e)}"
            }).encode('utf-8')
    
    @cherrypy.expose
    def switch(self):
        """Switch database adapter"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        if cherrypy.request.method != "POST":
            raise cherrypy.HTTPError(405, "Method Not Allowed")
        
        try:
            data = json.loads(cherrypy.request.body.read().decode('utf-8'))
            adapter_name = data.get('adapter')
            
            if not adapter_name:
                return json.dumps({
                    "success": False,
                    "message": "Missing 'adapter' field in request"
                }).encode('utf-8')
            
            success = self.database.switch_adapter(adapter_name)
            
            return json.dumps({
                "success": success,
                "message": f"Switched to {adapter_name}" if success else f"Failed to switch to {adapter_name}",
                "current_adapter": self.database.get_database_info().get("adapter_type"),
                "timestamp": datetime.now().isoformat()
            }).encode('utf-8')
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "message": f"Error switching adapter: {str(e)}"
            }).encode('utf-8')
    
    @cherrypy.expose
    def adapters(self):
        """List available database adapters"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        try:
            available_adapters = self.database.get_available_adapters()
            current_adapter = self.database.get_database_info().get("adapter_type")
            
            return json.dumps({
                "success": True,
                "available_adapters": available_adapters,
                "current_adapter": current_adapter,
                "timestamp": datetime.now().isoformat()
            }).encode('utf-8')
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "message": f"Error listing adapters: {str(e)}"
            }).encode('utf-8')


if __name__ == "__main__":
    #Register the service
    response = requests.post(
                "http://catalog:5001/services/",
                json={
                    "databaseAdapter": {
                        "url": "http://database_adapter",
                        "port": 3000,
                        "endpoints": {
                            "POST /write": "write health data to database",
                            "GET /users": "get all users with health data", 
                            "GET /read/<user_id>": "get user health data",
                            "GET /aggregated/<user_id>": "get aggregated user health data for charts",
                            "DELETE /delete/<user_id>": "delete user data",
                            "GET /info": "get database adapter information",
                            "POST /switch": "switch database adapter",
                            "GET /adapters": "list available adapters"
                        }
                    }
                }
            )
    
    # Configure CherryPy
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 3000,
        'tools.encode.on': True,
        'tools.encode.encoding': 'utf-8'
    })

    # CORS configuration
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
    
    print("Starting Database Adapter Service on port 3000...")
    cherrypy.quickstart(DatabaseAdapterService(), '/', conf)