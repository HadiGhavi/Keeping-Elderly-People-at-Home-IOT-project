import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
import time
from typing import Optional, Dict, Callable, Any, List
import socket
class MQTTService:
    def __init__(self, host: str, port: int, auth: Optional[Dict[str, str]] = None):
        self.host = host
        self.port = port
        self.auth = auth
        self._client = None
        self._message_handler = None
        self._connected = False

    # Publisher functionality
    def publish(self, topic: str, payload: Any, retain: bool = False, qos: int = 1) -> bool:
        try:
            print(self.host)
            print(self.port)
            publish.single(
                topic,
                payload=str(payload),
                hostname=self.host,
                port=self.port,
                retain=retain,
                qos=qos
            )
            return True
        except Exception as e:
            print(f"MQTT Publish Error: {e}")
            return False

    def disconnect(self):
        """Cleanly disconnect from MQTT broker"""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
            print("Disconnected from MQTT broker")