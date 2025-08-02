import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import requests
import time
import logging
from datetime import datetime
from Microservices.Notification.config import Config
import json
import cherrypy
TELEGRAM_TOKEN = Config.TELEGRAM["TELEGRAM_TOKEN"]

class Notification:
    @cherrypy.expose
    def sendNotif(self,**paraams):
            try:
                message = json.loads(cherrypy.request.body.read().decode('utf-8'))
                response = requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        json={ 
                            "chat_id": message["user_id"],
                            "text":f"Alert:{message}" ,
                            "parse_mode": "HTML"
                        },
                        timeout=10
                    )
                response.raise_for_status()
                logging.info(f"Telegram alert sent: {message}")
                return True
            except requests.exceptions.RequestException as e:
                logging.error(f"Telegram API failed: {e}")
                return False
                
            except ValueError:
                print(f"Invalid message format: {message}")
                return False
            except Exception as e:
                print(f"Processing error: {e}")
                return False
        
def setup_services():
    response = requests.post(
        f"http://localhost:5000/services/",
        json={
            "notification": {
            "url": "http://localhost",
            "port": 1500,
            "endpoints": {
                "Post /sendNotif/": "send notification"
              }
            }
        }
    )

if __name__ == "__main__":
    setup_services()
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 1500,
        'tools.encode.on': True,
        'tools.encode.encoding': 'utf-8'
    })
        
    cherrypy.quickstart(Notification(), '/')
