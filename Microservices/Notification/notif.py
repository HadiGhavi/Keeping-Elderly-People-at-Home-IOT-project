import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import requests
import cherrypy
import json
import threading
import time

from datetime import datetime, timedelta
from Microservices.Common.config import Config
from Microservices.Common.utils import register_service_with_catalog, ServiceRegistry
import logging
# Configure logging at module level
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('notification_service.log')
    ]
)
logger = logging.getLogger('NotificationService')

class NotificationService:
    def __init__(self):
        self.catalog_url = Config.SERVICES["catalog_url"]
        self.registry = ServiceRegistry()
        self.database_service_url = self.registry.get_service_url("databaseAdapter")
        self.telegram_token = Config.TELEGRAM_TOKEN
        
        # Track last notification time per user to avoid spam
        self.last_notification = {}  # user_id -> {"state": state, "timestamp": time}
        self.notification_cooldown = 300  # 5 minutes between similar notifications
        
        # Track last processed timestamp to avoid re-processing
        self.last_check_time = datetime.now() - timedelta(minutes=5)
        
        # Start monitoring thread
        logger.info("🔔 Starting notification monitoring service...")
        monitor_thread = threading.Thread(target=self.monitor_health_states, daemon=True)
        monitor_thread.start()
    
    @cherrypy.expose
    def index(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return json.dumps({
            "message": "Notification Service",
            "status": "monitoring",
            "endpoints": {
                "POST /sendNotif": "Manual notification (legacy)",
                "GET /status": "Get service status"
            }
        }).encode('utf-8')
    
    @cherrypy.expose
    def sendNotif(self):
        """Legacy manual notification endpoint (kept for backward compatibility)"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        if cherrypy.request.method != "POST":
            raise cherrypy.HTTPError(405, "Method Not Allowed")
        
        try:
            data = json.loads(cherrypy.request.body.read().decode('utf-8'))
            
            user_id = data.get("user_id")
            recipient_type = data.get("recipient_type", "patient")
            
            if recipient_type == "patient":
                success = self._send_patient_notification(data)
            elif recipient_type == "doctor":
                success = self._send_doctor_notification(data)
            else:
                return json.dumps({"success": False, "message": "Invalid recipient_type"}).encode('utf-8')
            
            return json.dumps({
                "success": success,
                "message": "Notification sent" if success else "Failed to send notification"
            }).encode('utf-8')
            
        except Exception as e:
            logger.info(f"Error in sendNotif: {e}")
            return json.dumps({"success": False, "message": str(e)}).encode('utf-8')
    
    @cherrypy.expose
    def status(self):
        """Get notification service status"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        return json.dumps({
            "status": "running",
            "last_check": self.last_check_time.isoformat(),
            "tracked_users": len(self.last_notification),
            "cooldown_seconds": self.notification_cooldown
        }).encode('utf-8')
    
    def monitor_health_states(self):
        """Continuously monitor database for critical health states"""
        logger.info("🔔 Notification monitoring started")
        
        while True:
            try:
                # Check every 30 seconds
                time.sleep(30)
                
                # Get all users from catalog
                users_response = requests.get(f"{self.catalog_url}/users", timeout=5)
                if users_response.status_code != 200:
                    logger.info("⚠️ Could not fetch users from catalog")
                    continue
                
                users = users_response.json()
                patients = [u for u in users if u.get("user_type") == "patient"]
                
                logger.info(f"🔍 Checking health states for {len(patients)} patients...")
                
                # Check each patient's recent data
                for patient in patients:
                    user_id = patient["user_chat_id"]
                    
                    # Get latest health data (last 2 minutes)
                    try:
                        data_response = requests.get(
                            f"{self.database_service_url}/read/{user_id}",
                            params={"hours": 1},  # Check last hour
                            timeout=10
                        )
                        
                        if data_response.status_code != 200:
                            continue
                        
                        result = data_response.json()
                        if not result.get("success") or not result.get("data"):
                            continue
                        
                        # Get most recent state
                        data = result["data"]
                        state_entries = [d for d in data if d.get("field") == "state"]
                        
                        if not state_entries:
                            continue
                        
                        # Sort by time and get latest
                        state_entries.sort(key=lambda x: x.get("time", ""), reverse=True)
                        latest_state_entry = state_entries[0]
                        latest_state = latest_state_entry.get("value")
                        
                        # Check if this is a critical state
                        if latest_state in ["risky", "dangerous"]:
                            # Check if we should send notification
                            if self._should_send_notification(user_id, latest_state):
                                logger.info(f"🚨 Critical state detected for user {user_id}: {latest_state}")
                                
                                # Get other vital signs from same time period
                                temp_entries = [d for d in data if d.get("field") == "temp"]
                                hr_entries = [d for d in data if d.get("field") == "heart_rate"]
                                oxygen_entries = [d for d in data if d.get("field") == "oxygen"]
                                
                                temp = temp_entries[0].get("value") if temp_entries else "N/A"
                                heart_rate = hr_entries[0].get("value") if hr_entries else "N/A"
                                oxygen = oxygen_entries[0].get("value") if oxygen_entries else "N/A"
                                
                                # Send notifications
                                self._process_critical_state(
                                    user_id=user_id,
                                    user_name=patient.get("full_name", f"User {user_id}"),
                                    state=latest_state,
                                    temp=temp,
                                    heart_rate=heart_rate,
                                    oxygen=oxygen,
                                    doctor_id=patient.get("doctor_id")
                                )
                                
                    except Exception as e:
                        logger.error(f"Error checking user {user_id}: {e}")
                        continue
                
                # Update last check time
                self.last_check_time = datetime.now()
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                import traceback
                traceback.print_exc()
    
    def _should_send_notification(self, user_id, current_state):
        """Check if we should send a notification based on cooldown"""
        current_time = time.time()
        
        if user_id not in self.last_notification:
            return True
        
        last_notif = self.last_notification[user_id]
        time_since_last = current_time - last_notif["timestamp"]
        
        # Send if:
        # 1. State has changed (e.g., risky -> dangerous)
        # 2. Cooldown period has passed for same state
        if last_notif["state"] != current_state:
            return True
        
        if time_since_last > self.notification_cooldown:
            return True
        
        return False
    
    def _process_critical_state(self, user_id, user_name, state, temp, heart_rate, oxygen, doctor_id):
        """Process and send notifications for critical health state"""
        
        # Prepare notification data
        notification_data = {
            "user_id": user_id,
            "user_name": user_name,
            "state": state,
            "temp": temp,
            "oxygen": oxygen,
            "heartRate": heart_rate
        }
        
        # Send patient notification
        logger.info(f"📱 Sending patient notification to {user_id}")
        patient_success = self._send_patient_notification(notification_data)
        
        # Send doctor notification if assigned
        if doctor_id:
            logger.info(f"👨‍⚕️ Sending doctor notification to {doctor_id}")
            doctor_data = {
                **notification_data,
                "doctor_id": doctor_id,
                "patient_name": user_name
            }
            doctor_success = self._send_doctor_notification(doctor_data)
        
        # Update last notification time
        self.last_notification[user_id] = {
            "state": state,
            "timestamp": time.time()
        }
    
    def _send_patient_notification(self, data):
        """Send notification to patient via Telegram"""
        try:
            user_id = data["user_id"]
            state = data["state"]
            temp = data["temp"]
            heart_rate = data["heartRate"]
            oxygen = data["oxygen"]
            
            # Determine emoji and severity
            if state == "dangerous":
                emoji = "🚨"
                severity = "CRITICAL"
            elif state == "risky":
                emoji = "⚠️"
                severity = "WARNING"
            else:
                return True  # Don't send for healthy states
            
            message = (
                f"{emoji} <b>Health Alert - {severity}</b>\n\n"
                f"Your health status requires attention:\n\n"
                f"Status: <b>{state.upper()}</b>\n"
                f"🌡️ Temperature: {temp}°C\n"
                f"❤️ Heart Rate: {heart_rate} BPM\n"
                f"🫁 Oxygen: {oxygen}%\n\n"
                f"Please monitor your condition carefully."
            )
            
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": user_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error sending patient notification: {e}")
            return False
    
    def _send_doctor_notification(self, data):
        """Send notification to doctor via Telegram"""
        try:
            doctor_id = data["doctor_id"]
            patient_name = data["patient_name"]
            patient_id = data["user_id"]
            state = data["state"]
            temp = data["temp"]
            heart_rate = data["heartRate"]
            oxygen = data["oxygen"]
            
            # Determine emoji and severity
            if state == "dangerous":
                emoji = "🚨"
                severity = "CRITICAL"
            elif state == "risky":
                emoji = "⚠️"
                severity = "WARNING"
            else:
                return True
            
            message = (
                f"{emoji} <b>Patient Alert - {severity}</b>\n\n"
                f"Patient: <b>{patient_name}</b> (ID: {patient_id})\n"
                f"Status: <b>{state.upper()}</b>\n\n"
                f"Vital Signs:\n"
                f"🌡️ Temperature: {temp}°C\n"
                f"❤️ Heart Rate: {heart_rate} BPM\n"
                f"🫁 Oxygen: {oxygen}%\n\n"
                f"Immediate attention may be required."
            )
            
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": doctor_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error sending doctor notification: {e}")
            return False


if __name__ == "__main__":
    # Register service
    register_service_with_catalog(
        service_name="notification",
        url="http://notification",
        port=1500,
        endpoints={
            "POST /sendNotif": "Send notification",
            "GET /status": "Get service status"
        }
    )
    
    # Configure CherryPy
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 1500,
        'tools.encode.on': True,
        'tools.encode.encoding': 'utf-8',
        'log.screen': True,  # Enable console output
        'log.access_file': '',  # Disable access log file
        'log.error_file': ''   # Disable error log file
    })
    
    # CORS
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
    
    logger.info("🔔 Starting Notification Service on port 1500...")
    cherrypy.quickstart(NotificationService(), '/', conf)