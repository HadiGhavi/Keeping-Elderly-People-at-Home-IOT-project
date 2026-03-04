import cherrypy
import json
import requests
from dataHandler import DataHandlerAdapter
from Microservices.Common.utils import register_service_with_catalog

class DataHandlerREST:
    exposed = True
    
    def __init__(self):
        self.handler = DataHandlerAdapter()
        # Start background MQTT and Retraining services
        self.handler.start_services()
        register_service_with_catalog(
            service_name="dataIngestion",
            url="http://data_ingestion",
            port=2500,
            endpoints={
                "GET /getUserData/<id>": "get user data",
                "GET /database/info": "db info"
            }
        )

    def GET(self, *uri, **params):
        if not uri:
            return json.dumps({"status": "Data Ingestion Running"}).encode('utf-8')
        
        command = uri[0]
        
        if command == "getUserData":
            user_id = uri[1]
            res = requests.get(f"{self.handler.database_service_url}/read/{user_id}")
            return res.content

        elif command == "database":
            action = uri[1] 
            res = requests.get(f"{self.handler.database_service_url}/{action}")
            return res.content

        raise cherrypy.HTTPError(501, "Not Implemented")

if __name__ == "__main__":

    data_rest = DataHandlerREST()
    
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True,
        }
    }
    cherrypy.tree.mount(data_rest, '/', conf)
    cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 2500})
    cherrypy.engine.start()
    cherrypy.engine.block()