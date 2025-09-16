import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import requests
import time
import logging
from datetime import datetime
import json
import cherrypy
TELEGRAM_TOKEN = "6605276431:AAHoPhbbqSSPR7z1VS56c7Cddp34xzvT2Og"

class Notification:

    @cherrypy.expose        
    def sendNotif(self, **params):
        try:
            message = json.loads(cherrypy.request.body.read().decode('utf-8'))
            
            # Format a proper alert message
            alert_text = f"🚨 Health Alert!\n\n"
            alert_text += f"User: {message.get('user_name', 'Unknown')}\n"
            alert_text += f"Status: {message.get('state', 'Unknown')}\n"
            alert_text += f"Temperature: {message.get('temp', 'N/A')}°C\n"
            alert_text += f"Heart Rate: {message.get('heartRate', 'N/A')} BPM\n"
            alert_text += f"Oxygen: {message.get('oxygen', 'N/A')}%\n"
            alert_text += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            response = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={ 
                    "chat_id": message["user_id"],
                    "text": alert_text,  # Use formatted text instead of raw object
                    "parse_mode": "HTML"
                },
                timeout=10
            )
            response.raise_for_status()
            logging.info(f"Telegram alert sent: {message}")
            
            # Return JSON string instead of boolean
            return json.dumps({"status": "success", "message": "Notification sent"})
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Telegram API failed: {e}")
            # Return JSON string for error case too
            return json.dumps({"status": "error", "message": str(e)})
            
        except ValueError as e:
            logging.error(f"Invalid message format: {e}")
            return json.dumps({"status": "error", "message": "Invalid JSON format"})
            
        except Exception as e:
            logging.error(f"Processing error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

        
def setup_services():
    response = requests.post(
        f"http://catalog:5001/services/",
        json={
            "notification": {
            "url": "http://notification",
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
