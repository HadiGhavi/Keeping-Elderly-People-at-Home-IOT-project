import cherrypy
import json
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
                "GET /read/<chat_id>": "start monitoring for user",
                "GET /stop/<chat_id>": "stop monitoring for user",
                "GET /status": "service status"
            }
        )

    def GET(self, *uri, **params):
        if not uri:
            return json.dumps({
                "message": "Monitor Service API",
                "endpoints": {
                    "GET /status": "Service status",
                    "GET /read/<chat_id>": "start monitoring for user",
                    "GET /stop/<chat_id>": "stop monitoring for user"
                }
            }).encode('utf-8')
        
        command = uri[0] # "read", "stop", or "status"
        
        if command == "status":
            return json.dumps({
                "status": "running",
                "last_check": self.monitor.last_check_time.isoformat(),
                "active_devices": len(self.monitor.device_threads)
            }).encode('utf-8')

        # Ensure we have at least a command and an ID for other commands
        if len(uri) < 2:
            raise cherrypy.HTTPError(400, "Bad Request: Missing chat_id in URL. Use /command/id")

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
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Content-Type', 'application/json')],
            'tools.encode.on': True,
            'tools.encode.encoding': 'utf-8'
        }
    }

    cherrypy.tree.mount(mon_rest, '/', conf)
    cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 3500})
    cherrypy.engine.start()
    cherrypy.engine.block()