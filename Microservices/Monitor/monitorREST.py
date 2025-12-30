import cherrypy
import json
import sys
from monitor import MonitorAdapter
from Microservices.Common.utils import register_service_with_catalog

class MonitorREST:
    exposed = True

    def __init__(self):
        self.monitor = MonitorAdapter()
        register_service_with_catalog(
            service_name="monitor",
            url="http://monitor",
            port=3500,
            endpoints={
                "GET /read/<id>": "start monitoring",
                "GET /stop/<id>": "stop monitoring"
            }
        )

    def GET(self, *uri, **params):
        if not uri:
            return json.dumps({"status": "Monitor Service Running"}).encode('utf-8')
        
        command = uri[0] # "read" or "stop"
        chat_id = uri[1] # <chat_id>

        if command == "read":
            success, result = self.monitor.start_monitoring(chat_id)
            if success:
                return json.dumps(result).encode('utf-8')
            raise cherrypy.HTTPError(404, result)

        elif command == "stop":
            success, stopped = self.monitor.stop_monitoring(chat_id)
            return json.dumps({"stopped_devices": stopped}).encode('utf-8')

        raise cherrypy.HTTPError(501, "Operation not supported")

if __name__ == "__main__":
    
    mon_rest = MonitorREST()
    
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True,
        }
    }
    cherrypy.tree.mount(mon_rest, '/', conf)
    cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 3500})
    cherrypy.engine.start()
    cherrypy.engine.block()