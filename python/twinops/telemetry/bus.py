"""In-process telemetry bus with optional MQTT publish/subscribe bridge."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

Subscriber = Callable[["TelemetryEvent"], None]
MqttMessageHandler = Callable[[str, bytes], None]


@dataclass(frozen=True)
class TelemetryEvent:
    topic: str
    prim: str
    attribute: str
    value: Any
    timestamp: str

    def to_observation_fragment(self) -> dict[str, Any]:
        return {
            "prim": self.prim,
            "attributes": {self.attribute: self.value},
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TelemetryBus:
    """Fan-out bus used by the simulator and live drift loop."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = threading.RLock()
        self._mqtt = None
        self._mqtt_ingest = None
        self._mqtt_host: str | None = None
        self._mqtt_port: int | None = None
        self._mqtt_ingest_topics: list[str] = []

    @property
    def mqtt_enabled(self) -> bool:
        with self._lock:
            return self._mqtt is not None

    @property
    def mqtt_ingest_enabled(self) -> bool:
        with self._lock:
            return self._mqtt_ingest is not None

    @property
    def mqtt_endpoint(self) -> dict[str, Any] | None:
        with self._lock:
            if self._mqtt_host is None or self._mqtt_port is None:
                return None
            return {
                "host": self._mqtt_host,
                "port": self._mqtt_port,
                "publish": self._mqtt is not None,
                "ingest": self._mqtt_ingest is not None,
                "ingestTopics": list(self._mqtt_ingest_topics),
            }

    def subscribe(self, callback: Subscriber) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def publish(self, event: TelemetryEvent) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
            mqtt = self._mqtt
        for callback in subscribers:
            try:
                callback(event)
            except Exception:  # noqa: BLE001 - isolate subscriber failures
                logger.exception("telemetry subscriber failed")
        if mqtt is not None:
            try:
                mqtt.publish(
                    event.topic,
                    json.dumps(
                        {
                            "prim": event.prim,
                            "attribute": event.attribute,
                            "value": event.value,
                            "timestamp": event.timestamp,
                            "source": "twinops",
                        }
                    ),
                )
            except Exception:  # noqa: BLE001
                logger.exception("mqtt publish failed")

    def enable_mqtt(self, host: str = "127.0.0.1", port: int = 1883) -> bool:
        """Best-effort MQTT publish bridge. Returns False if paho/broker unavailable."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.warning("paho-mqtt not installed; continuing with in-process bus only")
            return False

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="twinops-bus")
        try:
            client.connect(host, port, keepalive=30)
        except OSError as exc:
            logger.warning("mqtt broker unavailable at %s:%s (%s)", host, port, exc)
            return False
        client.loop_start()
        with self._lock:
            self._mqtt = client
            self._mqtt_host = host
            self._mqtt_port = port
        logger.info("mqtt publish bridge enabled %s:%s", host, port)
        return True

    def enable_mqtt_ingest(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
        *,
        topics: list[str],
        handler: MqttMessageHandler,
    ) -> bool:
        """Subscribe to broker topics and forward payloads to handler."""
        if not topics:
            return False
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.warning("paho-mqtt not installed; mqtt ingest disabled")
            return False

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="twinops-ingest"
        )

        def _on_message(_client: Any, _userdata: Any, msg: Any) -> None:
            try:
                handler(msg.topic, msg.payload)
            except Exception:  # noqa: BLE001
                logger.exception("mqtt ingest handler failed for %s", msg.topic)

        client.on_message = _on_message
        try:
            client.connect(host, port, keepalive=30)
        except OSError as exc:
            logger.warning("mqtt ingest broker unavailable at %s:%s (%s)", host, port, exc)
            return False

        for topic in topics:
            client.subscribe(topic)
        client.loop_start()
        with self._lock:
            self._mqtt_ingest = client
            self._mqtt_host = host
            self._mqtt_port = port
            self._mqtt_ingest_topics = list(topics)
        logger.info("mqtt ingest enabled %s:%s topics=%s", host, port, topics)
        return True

    def disable_mqtt(self) -> None:
        with self._lock:
            publish_client = self._mqtt
            ingest_client = self._mqtt_ingest
            self._mqtt = None
            self._mqtt_ingest = None
            self._mqtt_host = None
            self._mqtt_port = None
            self._mqtt_ingest_topics = []
        for client in (publish_client, ingest_client):
            if client is None:
                continue
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:  # noqa: BLE001
                logger.exception("mqtt disconnect failed")

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
