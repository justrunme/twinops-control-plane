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
        self._mqtt = client
        logger.info("mqtt bridge enabled %s:%s", host, port)
        return True

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
