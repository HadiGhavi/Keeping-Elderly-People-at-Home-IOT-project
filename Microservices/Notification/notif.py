import time
import requests
import logging
import threading
import json
from MyMQTT import * 
from datetime import datetime, timedelta
from Microservices.Common.config import Config
from Microservices.Common.utils import ServiceRegistry

logger = logging.getLogger('NotificationService')

class NotificationAdapter:
    def __init__(self):
        self.registry = ServiceRegistry()
        self.mqtt_info = self.registry.get_service_info("mqtt")
        self.catalog_url = Config.SERVICES["catalog_url"]
        self.telegram_token = Config.TELEGRAM_TOKEN
        self.last_notification = {}
        self.notification_cooldown = 300 
        
        self.mqtt_client = MyMQTT(
            clientID="NotificationService",
            broker=self.mqtt_info["url"],
            port=self.mqtt_info["port"],
            notifier=self 
        )

    def start_listening(self):
        self.mqtt_client.start() 
        self.mqtt_client.mySubscribe("iot/notifications/#") 

    def notify(self, topic, payload):
        try:
            alert_data = json.loads(payload)
            user_id = alert_data.get("user_id")
            state = alert_data.get("state")
            vitals = alert_data.get("vitals", {})

            if self._should_send(user_id, state):
                # Update state BEFORE sending to prevent race conditions
                uid_str = str(user_id)
                self.last_notification[uid_str] = {"state": state, "timestamp": time.time()}
                
                user_res = requests.get(f"{self.catalog_url}/users/{user_id}", timeout=5)
                if user_res.status_code == 200:
                    patient_info = user_res.json()
                    self._send_alerts(patient_info, state, vitals)
                else:
                    logger.warning(f"User {user_id} not found in catalog (Status {user_res.status_code})")
        except Exception as e:
            logger.error(f"Error in MyMQTT notify: {e}")
   
    def _should_send(self, user_id, current_state):
        current_time = time.time()
        uid_str = str(user_id)
        if uid_str not in self.last_notification: return True
        last = self.last_notification[uid_str]
        return last["state"] != current_state or (current_time - last["timestamp"] > self.notification_cooldown)
    
    def _send_telegram(self, chat_id, text):
        def perform_request():
            try:
                url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status() 
            except Exception as e:
                logger.error(f"Failed to send Telegram message to {chat_id}: {e}")
        # This returns control to the main loop IMMEDIATELY
        threading.Thread(target=perform_request, daemon=True).start()
        
    def _send_alerts(self, patient, state, vitals_dict):
        user_id = patient["user_chat_id"]
        msg = self._format_message(patient.get("full_name"), state, vitals_dict)
        
        self._send_telegram(user_id, msg)
        if patient.get("doctor_id"):
            self._send_telegram(patient["doctor_id"], f"DOC ALERT: {msg}")

    def _format_message(self, name, state, vitals):
        emoji = "🚨" if state == "dangerous" else "⚠️"
        return (f"{emoji} <b>Health Alert</b>\n"
                f"Patient: {name}\n"
                f"Status: {state.upper()}\n"
                f"Temp: {vitals.get('temp', 'N/A')}°C\n"
                f"HR: {vitals.get('heart_rate', 'N/A')} BPM\n"
                f"O2: {vitals.get('oxygen', 'N/A')}%")