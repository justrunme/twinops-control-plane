"""In-process telemetry bus with optional MQTT publish bridge."""

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
        self._mqtt_host: str | None = None
        self._mqtt_port: int | None = None

    @property
    def mqtt_enabled(self) -> bool:
        with self._lock:
            return self._mqtt is not None

    @property
    def mqtt_endpoint(self) -> dict[str, Any] | None:
        with self._lock:
            if self._mqtt is None or self._mqtt_host is None or self._mqtt_port is None:
                return None
            return {"host": self._mqtt_host, "port": self._mqtt_port}

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
                        }
                    ),
                )
            except Exception:  # noqa: BLE001
                logger.exception("mqtt publish failed")

    def enable_mqtt(self, host: str = "127.0.0.1", port: int = 1883) -> bool:
        """Best-effort MQTT bridge. Returns False if paho/broker unavailable."""
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
        logger.info("mqtt bridge enabled %s:%s", host, port)
        return True

    def disable_mqtt(self) -> None:
        with self._lock:
            client = self._mqtt
            self._mqtt = None
            self._mqtt_host = None
            self._mqtt_port = None
        if client is None:
            return
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:  # noqa: BLE001
            logger.exception("mqtt disconnect failed")

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
