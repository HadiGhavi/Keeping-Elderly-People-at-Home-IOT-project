import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import cherrypy
import requests
import json
import logging
from datetime import datetime
from Microservices.Common.config import Config
from Microservices.Common.utils import register_service_with_catalog
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        self.telegram_token = Config.TELEGRAM_TOKEN
        self.telegram_api_url = f"https://api.telegram.org/bot{self.telegram_token}"
        
    
    @cherrypy.expose
    def index(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return json.dumps({
            "message": "Notification Service API",
            "endpoints": {
                "POST /sendNotif": "Send notification to user or doctor"            },
            "status": "active"
        }).encode('utf-8')
    
    
    @cherrypy.expose
    @cherrypy.tools.json_in()
    def sendNotif(self):
        """Send notification via Telegram"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        if cherrypy.request.method != "POST":
            raise cherrypy.HTTPError(405, "Method Not Allowed")
        
        try:
            # Get the JSON data from the request
            data = cherrypy.request.json
            logger.info(f"Received notification request: {data}")
            
            # Validate required fields
            required_fields = ['user_id', 'user_name', 'state', 'temp', 'oxygen', 'heartRate']
            if not all(field in data for field in required_fields):
                logger.error(f"Missing required fields. Required: {required_fields}, Received: {list(data.keys())}")
                return json.dumps({
                    "success": False,
                    "message": f"Missing required fields: {required_fields}"
                }).encode('utf-8')
            
            recipient_type = data.get('recipient_type', 'patient')
            
            if recipient_type == 'patient':
                # Send notification to patient
                success, message = self.send_patient_notification(data)
            elif recipient_type == 'doctor':
                # Send notification to doctor
                success, message = self.send_doctor_notification(data)
            else:
                logger.error(f"Unknown recipient type: {recipient_type}")
                return json.dumps({
                    "success": False,
                    "message": f"Unknown recipient type: {recipient_type}"
                }).encode('utf-8')
            
            return json.dumps({
                "success": success,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }).encode('utf-8')
            
        except Exception as e:
            logger.error(f"Error in sendNotif: {e}")
            import traceback
            traceback.print_exc()
            return json.dumps({
                "success": False,
                "message": f"Internal error: {str(e)}"
            }).encode('utf-8')
    
    def send_patient_notification(self, data):
        """Send health alert notification to patient"""
        try:
            user_id = data['user_id']
            user_name = data['user_name']
            state = data['state']
            temp = data['temp']
            oxygen = data['oxygen']
            heart_rate = data['heartRate']
            
            # Create patient notification message
            if state == 'dangerous':
                emoji = "🚨"
                urgency = "CRITICAL ALERT"
                message = f"{emoji} {urgency}\n\n"
                message += f"Dear {user_name},\n\n"
                message += f"Your health readings show concerning values:\n"
                message += f"🌡️ Temperature: {temp}°C\n"
                message += f"❤️ Heart Rate: {heart_rate} BPM\n"
                message += f"🫁 Oxygen: {oxygen}%\n\n"
                message += f"⚠️ Please seek immediate medical attention or contact your doctor.\n\n"
                message += f"If this is an emergency, call emergency services immediately."
            
            elif state == 'risky':
                emoji = "⚠️"
                urgency = "Health Warning"
                message = f"{emoji} {urgency}\n\n"
                message += f"Dear {user_name},\n\n"
                message += f"Your health readings require attention:\n"
                message += f"🌡️ Temperature: {temp}°C\n"
                message += f"❤️ Heart Rate: {heart_rate} BPM\n"
                message += f"🫁 Oxygen: {oxygen}%\n\n"
                message += f"Please monitor your symptoms and consider contacting your doctor.\n"
                message += f"Take care and rest if needed."
            
            else:
                # Normal state - usually don't send notifications for normal readings
                return True, "Normal state - no notification sent"
            
            # Send the message via Telegram
            return self.send_telegram_message(user_id, message)
            
        except Exception as e:
            logger.error(f"Error sending patient notification: {e}")
            return False, f"Failed to send patient notification: {str(e)}"
    
    def send_doctor_notification(self, data):
        """Send patient alert notification to doctor"""
        try:
            patient_name = data.get('patient_name', data['user_name'])
            patient_id = data['user_id']
            doctor_id = data['doctor_id']
            state = data['state']
            temp = data['temp']
            oxygen = data['oxygen']
            heart_rate = data['heartRate']
            
            # Create doctor notification message
            if state == 'dangerous':
                emoji = "🚨"
                urgency = "CRITICAL PATIENT ALERT"
                message = f"{emoji} {urgency}\n\n"
                message += f"Doctor Alert - Immediate Attention Required\n\n"
                message += f"Patient: {patient_name} (ID: {patient_id})\n"
                message += f"Status: DANGEROUS\n\n"
                message += f"Critical Vitals:\n"
                message += f"🌡️ Temperature: {temp}°C\n"
                message += f"❤️ Heart Rate: {heart_rate} BPM\n"
                message += f"🫁 Oxygen: {oxygen}%\n\n"
                message += f"⚠️ This patient requires immediate medical evaluation.\n"
                message += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            elif state == 'risky':
                emoji = "⚠️"
                urgency = "Patient Health Warning"
                message = f"{emoji} {urgency}\n\n"
                message += f"Patient: {patient_name} (ID: {patient_id})\n"
                message += f"Status: RISKY\n\n"
                message += f"Concerning Vitals:\n"
                message += f"🌡️ Temperature: {temp}°C\n"
                message += f"❤️ Heart Rate: {heart_rate} BPM\n"
                message += f"🫁 Oxygen: {oxygen}%\n\n"
                message += f"📞 Consider contacting this patient for follow-up.\n"
                message += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            else:
                # Normal state - don't send notifications for normal readings
                return True, "Normal state - no doctor notification sent"
            
            # Send the message to doctor via Telegram
            return self.send_telegram_message(doctor_id, message)
            
        except Exception as e:
            logger.error(f"Error sending doctor notification: {e}")
            return False, f"Failed to send doctor notification: {str(e)}"
    
    def send_telegram_message(self, chat_id, message):
        """Send message via Telegram Bot API"""
        try:
            url = f"{self.telegram_api_url}/sendMessage"
            
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",  # Allow HTML formatting if needed
                "disable_web_page_preview": True
            }
            
            logger.info(f"Sending Telegram message to {chat_id}")
            logger.debug(f"Message payload: {payload}")
            
            response = requests.post(url, json=payload, timeout=10)
            
            logger.info(f"Telegram API response: {response.status_code}")
            logger.debug(f"Response content: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    logger.info(f"Message sent successfully to {chat_id}")
                    return True, "Message sent successfully"
                else:
                    error_msg = result.get("description", "Unknown error")
                    logger.error(f"Telegram API error: {error_msg}")
                    return False, f"Telegram API error: {error_msg}"
            else:
                logger.error(f"HTTP error: {response.status_code} - {response.text}")
                return False, f"HTTP error: {response.status_code}"
                
        except requests.exceptions.Timeout:
            logger.error("Telegram API request timed out")
            return False, "Request timeout"
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            return False, f"Request error: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Unexpected error: {str(e)}"


if __name__ == "__main__":
    register_service_with_catalog(service_name="notification", 
                                  url="http://notification",
                                  port=1500,
                                  endpoints={
                                        "POST /sendNotif": "Send notification",
                                        "GET /": "Service information"
                                  })
    
    # Configure CherryPy
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 1500,
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
    
    logger.info("Starting Notification Service on port 1500...")
    cherrypy.quickstart(NotificationService(), '/', conf)