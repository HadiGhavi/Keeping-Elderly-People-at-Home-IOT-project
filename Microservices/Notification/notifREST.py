import cherrypy
import json
import logging
from notif import NotificationAdapter
from Microservices.Common.utils import register_service_with_catalog

class NotificationREST:
    exposed = True

    def __init__(self):
        self.adapter = NotificationAdapter()
        self.adapter.start_listening()
        register_service_with_catalog(
            service_name="notification",
            url="http://notification",
            port=1500,
            endpoints={"GET /status": "Service status"}
        )

    def GET(self, *uri):
        if uri and uri[0] == "status":
            return json.dumps({
                "status": "running",
                "last_check": self.adapter.last_check_time.isoformat(),
                "tracked_users": len(self.adapter.last_notification)
            }).encode('utf-8')
        return json.dumps({"message": "Notification Service API"}).encode('utf-8')


if __name__ == "__main__":
    
    notif_rest = NotificationREST()
    
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True,
        }
    }
    cherrypy.tree.mount(notif_rest, '/', conf)
    cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 1500})
    cherrypy.engine.start()
    cherrypy.engine.block()