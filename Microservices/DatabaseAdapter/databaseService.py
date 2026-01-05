import cherrypy
import json
import pandas as pd
from influxdbAdapter import InfluxDBAdapter
from Microservices.Common.utils import register_service_with_catalog

class DatabaseREST():
    exposed = True

    def __init__(self):
        self.adapter = InfluxDBAdapter()
        register_service_with_catalog(
            service_name="databaseAdapter",
            url="http://database_adapter",
            port=3000,
            endpoints={
                "GET /read/<id>": "read raw health data",
                "GET /aggregated/<id>": "get 5-min averaged vitals",
                "POST /write": "save new health record",
                "GET /info": "get database connection info"
                }
        )

    def GET(self, *uri, **params):
        try:
            command = uri[0] # e.g., "read"
            
            if command == "read":
                user_id = uri[1]
                hours = params.get('hours', 24)
                success, data = self.adapter.get_user_health_data(user_id, hours)
                if success:
                    return json.dumps({"success": True, "data": data})
                else:
                    raise cherrypy.HTTPError(500, data)
            
            elif command == "info":
                return json.dumps({"host": self.adapter.host, "bucket": self.adapter.bucket})

            elif command == "aggregated":
                user_id = uri[1]
                hours = int(params.get('hours', 24))
                
                # 1. Get raw data from the adapter
                success, raw_data = self.adapter.get_user_health_data(user_id, hours)
                
                if not success or not raw_data:
                    return json.dumps({"success": False, "message": "No data"}).encode('utf-8')

                # 2. Convert to pandas DataFrame 
                df = pd.DataFrame(raw_data)
                df['time'] = pd.to_datetime(df['time'])
                
                # 3. Separate numeric fields for averaging 
                numeric_fields = ['temp', 'heart_rate', 'oxygen']
                numeric_df = df[df['field'].isin(numeric_fields)].copy()
                numeric_df['value'] = pd.to_numeric(numeric_df['value'])
                
                # 4. Pivot and Resample (e.g., 5-minute windows) 
                # We pivot so fields become columns: [time, temp, heart_rate, oxygen]
                pivot_df = numeric_df.pivot(index='time', columns='field', values='value')
                resampled = pivot_df.resample('5min').mean().dropna(how='all')
                
                # 5. Format for JSON response
                aggregated_results = []
                for timestamp, row in resampled.iterrows():
                    entry = {"time": timestamp.isoformat()}
                    entry.update(row.to_dict())
                    aggregated_results.append(entry)

                return json.dumps({
                    "success": True,
                    "user_id": user_id,
                    "data": aggregated_results
                }).encode('utf-8')

            else:
                raise cherrypy.HTTPError(501, "Command not found")
        except Exception as e:
            raise cherrypy.HTTPError(400, f"Error: {str(e)}")
        

    def POST(self, *uri):
        command = uri[0]
        body = cherrypy.request.body.read()
        data = json.loads(body.decode('utf-8'))

        if command == "write":
            success, message = self.adapter.write_health_data(
                data['user_id'], data['user_name'], 
                data['temp'], data['heart_rate'], 
                data['oxygen'], data['state']
            )
            return json.dumps({"success": success, "message": message})
        
        else:
            raise cherrypy.HTTPError(501, "No operation!")

if __name__ == '__main__':
    db_rest = DatabaseREST()
    
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True,
        }
    }
    cherrypy.tree.mount(db_rest, '/', conf)
    cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 3000})
    cherrypy.engine.start()
    cherrypy.engine.block()