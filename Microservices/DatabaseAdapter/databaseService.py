import cherrypy
import json
from datetime import datetime
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
                "GET /info": "get database connection info",
                "GET /status": "service status"
                }
        )
        self.last_check_time = datetime.now()

    def GET(self, *uri, **params):
        self.last_check_time = datetime.now()
        try:
            if not uri or uri[0] == "status":
                return json.dumps({
                    "status": "running",
                    "last_check": self.last_check_time.isoformat(),
                    "endpoints": {
                        "GET /read/<id>": "read raw health data",
                        "GET /aggregated/<id>": "get 5-min averaged vitals",
                        "POST /write": "save new health record",
                        "GET /info": "get database connection info"
                    }
                }).encode('utf-8')
            
            command = uri[0]
            
            if command == "info":
                return json.dumps({
                    "database": "InfluxDB",
                    "last_check": self.last_check_time.isoformat()
                }).encode('utf-8')

            # Check if we actually have an ID in the URL for other commands
            if len(uri) < 2:
                raise cherrypy.HTTPError(400, "Missing user_id in request path")

            user_id = uri[1]
            hours = params.get('hours', 24)

            if command == "read":
                success, data = self.adapter.get_user_health_data(user_id, hours, aggregate=False)
                if success:
                    return json.dumps({"success": True, "data": data}).encode('utf-8')
                raise Exception(data) 

            elif command == "aggregated":
                success, data = self.adapter.get_user_health_data(user_id, hours, aggregate=True)
                if success:
                    return json.dumps({"success": True, "data": data}).encode('utf-8')
                raise Exception(data)

        except Exception as e:
            print(f"Database Service Error: {str(e)}")
            raise cherrypy.HTTPError(400, f"Adapter Error: {str(e)}")
        

    def POST(self, *uri):
        command = uri[0]
        body = cherrypy.request.body.read()
        data = json.loads(body.decode('utf-8'))

        if command == "write":
            self.last_check_time = datetime.now()
            success, message = self.adapter.write_health_data(
                data['user_id'], data['user_name'], 
                data['temp'], data['heart_rate'], 
                data['oxygen'], data['state']
            )
            return json.dumps({"success": success, "message": message}).encode('utf-8')
        
        else:
            raise cherrypy.HTTPError(501, "No operation!")

if __name__ == '__main__':
    db_rest = DatabaseREST()
    
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True,
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Content-Type', 'application/json')],
            'tools.encode.on': True,
            'tools.encode.encoding': 'utf-8'
        }
    }
    cherrypy.tree.mount(db_rest, '/', conf)
    cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 3000})
    cherrypy.engine.start()
    cherrypy.engine.block()

    