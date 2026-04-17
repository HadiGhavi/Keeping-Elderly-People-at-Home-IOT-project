import time
import requests
import logging
import threading
import json
from datetime import datetime
from MyMQTT import * 
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
        self.last_check_time = datetime.now()
        
        self.mqtt_client = MyMQTT(
            clientID="NotificationService",
            broker=self.mqtt_info["url"],
            port=self.mqtt_info["port"],
            notifier=self 
        )

    def start_listening(self):
        print("Notification Service: Started listening for notifications...")
        self.mqtt_client.start() 
        self.mqtt_client.mySubscribe("iot/notifications/#") 

    def notify(self, topic, payload):
        self.last_check_time = datetime.now()
        try:
            alert_data = json.loads(payload)
            user_id = alert_data.get("user_id")
            state = alert_data.get("state")
            vitals = alert_data.get("vitals", {})
            print(f"Notification received for user {user_id}: state={state}")

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
        chat_id = patient["user_chat_id"]
        full_name = patient.get("full_name", "Unknown")
        
        # Format and send patient message
        patient_msg = self._format_patient_message(full_name, state, vitals_dict)
        print(f"Sending Telegram alert to patient {chat_id} ({full_name}) - State: {state}")
        self._send_telegram(chat_id, patient_msg)
        
        # Format and send doctor message if exists
        if patient.get("doctor_id"):
            doctor_msg = self._format_doctor_message(full_name, chat_id, state, vitals_dict)
            print(f"Sending Telegram alert to doctor {patient.get('doctor_id')}")
            self._send_telegram(patient["doctor_id"], doctor_msg)

    def _format_patient_message(self, name, state, vitals):
        emoji = "🚨" if state == "dangerous" else "⚠️"
        severity = "CRITICAL" if state == "dangerous" else "WARNING"
        
        temp = vitals.get('temp', 'N/A')
        heart_rate = vitals.get('heart_rate', 'N/A')
        oxygen = vitals.get('oxygen', 'N/A')

        return (
            f"{emoji} <b>Health Alert - {severity}</b>\n\n"
            f"Your health status requires attention:\n\n"
            f"Status: <b>{state.upper()}</b>\n"
            f"🌡️ Temperature: {temp}°C\n"
            f"❤️ Heart Rate: {heart_rate} BPM\n"
            f"🫁 Oxygen: {oxygen}%\n\n"
            f"Please monitor your condition carefully."
        )

    def _format_doctor_message(self, patient_name, patient_id, state, vitals):
        emoji = "🚨" if state == "dangerous" else "⚠️"
        severity = "CRITICAL" if state == "dangerous" else "WARNING"
        
        temp = vitals.get('temp', 'N/A')
        heart_rate = vitals.get('heart_rate', 'N/A')
        oxygen = vitals.get('oxygen', 'N/A')

        return (
            f"{emoji} <b>Patient Alert - {severity}</b>\n\n"
            f"Patient: <b>{patient_name}</b> (ID: {patient_id})\n"
            f"Status: <b>{state.upper()}</b>\n\n"
            f"Vital Signs:\n"
            f"🌡️ Temperature: {temp}°C\n"
            f"❤️ Heart Rate: {heart_rate} BPM\n"
            f"🫁 Oxygen: {oxygen}%\n\n"
            f"Immediate attention may be required."
        )