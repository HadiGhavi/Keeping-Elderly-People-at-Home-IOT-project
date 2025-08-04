import paho.mqtt.client as mqtt
import time
from typing import Optional, Dict, Callable, Any, List

class MQTTService:
    def __init__(self, host: str, port: int, auth: Optional[Dict[str, str]] = None):
        self.host = host
        self.port = port
        self.auth = auth
        self._client = None
        self._message_handler = None
        self._connected = False

    # Subscriber functionality
    def subscribe(self, topics: List[str], message_handler: Callable[[str, str], None]) -> None:
        self._message_handler = message_handler
        self._topics = topics  # Store the topics
        
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        
        if self.auth:
            self._client.username_pw_set(self.auth["username"], self.auth["password"])
        
        self._connect_with_retry()
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"Connected to MQTT broker at {self.host}:{self.port}")
            self._connected = True
            for topic in self._topics:
                client.subscribe(topic)
                print(f"Subscribed to {topic}")
        else:
            print(f"Connection failed with reason code: {reason_code}")

    def _on_message(self, client, userdata, msg):
        if self._message_handler:
            try:
                self._message_handler(msg.topic, msg.payload.decode())
            except Exception as e:
                print(f"Error in message handler: {e}")

    def _connect_with_retry(self, max_retries: int = 5, retry_interval: int = 5):
        retry_count = 0
        while retry_count < max_retries and not self._connected:
            try:
                self._client.connect(self.host, self.port, keepalive=60)
                self._connected = True
            except Exception as e:
                retry_count += 1
                print(f"Connection failed (attempt {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    time.sleep(retry_interval)
        
        if not self._connected:
            raise ConnectionError(f"Failed to connect to MQTT broker after {max_retries} attempts")

    def disconnect(self):
        """Cleanly disconnect from MQTT broker"""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
            print("Disconnected from MQTT broker")