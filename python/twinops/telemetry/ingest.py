"""MQTT → observed-state ingest for TwinOps live demos."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any

from twinops.telemetry.bus import TelemetryBus
from twinops.telemetry.reliability import SensorTracker

logger = logging.getLogger(__name__)

IGNORE_SOURCES = frozenset({"twinops", "twinops-bus", "twinops-simulator"})


@dataclass(frozen=True)
class TopicBinding:
    topic: str
    prim: str
    attribute: str


class ObservationIngest:
    """Maps inbound MQTT topics onto observed twin attributes.

    Reliability gates (per sensor / topic):
    - out-of-order sequence or timestamp → drop
    - duplicate message id / sequence within dedupe window → drop
    - TTL without fresh reading → STALE/UNKNOWN (never left as 'normal')
    - bounded clock skew → reject/quarantine without advancing sensor state
    """

    def __init__(
        self,
        bindings: list[TopicBinding] | None = None,
        *,
        strict_schema: bool = False,
        ttl_seconds: float = 30.0,
        dedupe_window_seconds: float = 60.0,
        max_skew_seconds: float = 30.0,
        tracker: SensorTracker | None = None,
    ) -> None:
        self._bindings = {item.topic: item for item in (bindings or [])}
        self._overrides: dict[str, dict[str, Any]] = {}
        self._sensor_status: dict[str, str] = {}
        self._lock = threading.RLock()
        self.strict_schema = strict_schema
        self.tracker = tracker or SensorTracker(
            ttl_seconds=ttl_seconds,
            dedupe_window_seconds=dedupe_window_seconds,
            max_skew_seconds=max_skew_seconds,
        )
        self.received = 0
        self.ignored = 0
        self.rejected = 0
        self.duplicates_dropped = 0
        self.out_of_order_dropped = 0
        self.clock_skew_violations = 0
        self.last_topic: str | None = None
        self.last_value: Any = None

    @classmethod
    def from_manifest_mappings(
        cls,
        mappings: list[Any],
        *,
        strict_schema: bool = False,
        ttl_seconds: float = 30.0,
        dedupe_window_seconds: float = 60.0,
        max_skew_seconds: float = 30.0,
    ) -> ObservationIngest:
        bindings = [
            TopicBinding(
                topic=str(item.topic),
                prim=str(item.prim),
                attribute=str(item.attribute),
            )
            for item in mappings
            if getattr(item, "topic", None) and getattr(item, "prim", None)
        ]
        return cls(
            bindings,
            strict_schema=strict_schema,
            ttl_seconds=ttl_seconds,
            dedupe_window_seconds=dedupe_window_seconds,
            max_skew_seconds=max_skew_seconds,
        )

    @property
    def topics(self) -> list[str]:
        return sorted(self._bindings)

    def binding_for(self, topic: str) -> TopicBinding | None:
        return self._bindings.get(topic)

    def status(self) -> dict[str, Any]:
        with self._lock:
            reliability = self.tracker.status()
            return {
                "enabled": True,
                "topics": self.topics,
                "received": self.received,
                "ignored": self.ignored,
                "rejected": self.rejected,
                "duplicatesDropped": self.duplicates_dropped,
                "outOfOrderDropped": self.out_of_order_dropped,
                "clockSkewViolations": self.clock_skew_violations,
                "strictSchema": self.strict_schema,
                "lastTopic": self.last_topic,
                "lastValue": self.last_value,
                "overridePrims": sorted(self._overrides),
                "sensorStatus": dict(self._sensor_status),
                "reliability": reliability,
                "staleSensors": reliability.get("staleSensors", 0),
                "conditions": self._conditions_unlocked(reliability),
            }

    def _conditions_unlocked(self, reliability: dict[str, Any]) -> list[dict[str, Any]]:
        conditions = []
        stale = int(reliability.get("staleSensors") or 0)
        metrics = reliability.get("metrics") or {}
        skew = int(metrics.get("clockSkewViolations") or reliability.get("clockSkewSensors") or 0)
        if skew == 0:
            skew = int(self.clock_skew_violations)
        conditions.append(
            {
                "type": "TelemetryFresh",
                "status": "False" if stale else "True",
                "reason": "StaleSensors" if stale else "Fresh",
                "message": f"{stale} stale sensor(s)" if stale else "all sensors fresh",
            }
        )
        conditions.append(
            {
                "type": "TelemetryClockSkew",
                "status": "True" if skew else "False",
                "reason": "SkewDetected" if skew else "WithinBound",
                "message": f"{skew} sensor(s) exceed skew bound"
                if skew
                else "clock skew within bound",
            }
        )
        return conditions

    def handle_message(self, topic: str, payload: bytes | str) -> bool:
        """Apply one MQTT message. Returns True when an override was stored."""
        binding = self._bindings.get(topic)
        if binding is None:
            with self._lock:
                self.ignored += 1
            return False

        raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        if self.strict_schema and not self._payload_schema_ok(raw):
            with self._lock:
                self.rejected += 1
            logger.warning("mqtt ingest rejected invalid payload on %s", topic)
            return False
        value, source, meta = self._parse_payload(raw)
        if source in IGNORE_SOURCES:
            with self._lock:
                self.ignored += 1
            return False

        result = self.tracker.accept(
            topic,
            value,
            sequence=meta.get("sequence"),
            timestamp=meta.get("timestamp"),
            message_id=meta.get("message_id"),
            epoch=meta.get("epoch"),
            session_id=meta.get("session_id"),
        )
        with self._lock:
            if result.clock_skew:
                self.clock_skew_violations += 1
            if result.duplicate:
                self.duplicates_dropped += 1
                return False
            if result.out_of_order:
                self.out_of_order_dropped += 1
                return False
            if not result.accepted:
                self.rejected += 1
                return False

            self._overrides.setdefault(binding.prim, {})[binding.attribute] = result.value
            # Surface reliability status on the prim (never mask STALE as normal).
            self._sensor_status[topic] = result.status
            if binding.attribute == "twinops:status" or result.status in {
                "STALE",
                "UNKNOWN",
                "CLOCK_SKEW",
            }:
                status_attr = "twinops:telemetryStatus"
                self._overrides.setdefault(binding.prim, {})[status_attr] = result.status
                if result.status in {"STALE", "UNKNOWN"} and binding.attribute == "twinops:status":
                    self._overrides[binding.prim][binding.attribute] = result.status
            self.received += 1
            self.last_topic = topic
            self.last_value = result.value
        logger.info(
            "mqtt ingest %s → %s.%s = %r (%s)",
            topic,
            binding.prim,
            binding.attribute,
            result.value,
            result.status,
        )
        return True

    def apply_stale(self) -> list[str]:
        """Refresh TTL and project STALE/UNKNOWN into observation overrides."""
        stale_topics = self.tracker.refresh_stale()
        with self._lock:
            for topic in stale_topics:
                binding = self._bindings.get(topic)
                if binding is None:
                    continue
                state = self.tracker.snapshot().get(topic)
                if state is None:
                    continue
                self._sensor_status[topic] = state.status
                attrs = self._overrides.setdefault(binding.prim, {})
                attrs["twinops:telemetryStatus"] = state.status
                if binding.attribute == "twinops:status":
                    attrs[binding.attribute] = state.status
                elif state.status in {"STALE", "UNKNOWN"}:
                    # Keep last numeric reading but mark telemetry not synced.
                    attrs["twinops:telemetryStatus"] = state.status
        return stale_topics

    def merge_observations(self, observed_raw: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of observed_raw with MQTT overrides applied."""
        self.apply_stale()
        with self._lock:
            overrides = {
                prim: dict(attrs) for prim, attrs in self._overrides.items()
            }
        if not overrides:
            return observed_raw

        merged = dict(observed_raw)
        observations = []
        by_prim = {
            item["prim"]: dict(item.get("attributes") or {})
            for item in observed_raw.get("observations") or []
            if isinstance(item, dict) and item.get("prim")
        }
        for prim, attrs in overrides.items():
            by_prim.setdefault(prim, {}).update(attrs)
        for prim, attrs in sorted(by_prim.items()):
            observations.append({"prim": prim, "attributes": attrs})
        merged["observations"] = observations
        merged["source"] = "twinops-simulator+mqtt-ingest"
        merged["timestamp"] = observed_raw.get("timestamp") or TelemetryBus.now()
        return merged

    def clear(self) -> None:
        with self._lock:
            self._overrides.clear()
            self._sensor_status.clear()

    @staticmethod
    def _payload_schema_ok(raw: str) -> bool:
        """When payload is a JSON object with `schema`, require twinops.mqtt.payload.v1."""
        from twinops.telemetry.payload import validate_mqtt_payload

        text = raw.strip()
        if not text:
            return False
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Scalar legacy payloads are allowed even in strict mode.
            return True
        if not isinstance(data, dict):
            return True
        if "schema" not in data:
            return True
        return not validate_mqtt_payload(data)

    @staticmethod
    def _parse_payload(raw: str) -> tuple[Any, str | None, dict[str, Any]]:
        text = raw.strip()
        meta: dict[str, Any] = {}
        if not text:
            return None, None, meta
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return ObservationIngest._coerce_scalar(text), None, meta
        if isinstance(data, dict):
            source = data.get("source")
            if "sequence" in data:
                try:
                    meta["sequence"] = int(data["sequence"])
                except (TypeError, ValueError):
                    pass
            if "seq" in data and "sequence" not in meta:
                try:
                    meta["sequence"] = int(data["seq"])
                except (TypeError, ValueError):
                    pass
            if "timestamp" in data:
                meta["timestamp"] = data["timestamp"]
            if "messageId" in data:
                meta["message_id"] = str(data["messageId"])
            elif "id" in data and data.get("schema") == "twinops.mqtt.payload.v1":
                meta["message_id"] = str(data["id"])
            if data.get("epoch") is not None:
                meta["epoch"] = str(data["epoch"])
            if data.get("sessionId") is not None:
                meta["session_id"] = str(data["sessionId"])
            elif data.get("session_id") is not None:
                meta["session_id"] = str(data["session_id"])
            if "value" in data:
                return data["value"], str(source) if source is not None else None, meta
            return data, str(source) if source is not None else None, meta
        return data, None, meta

    @staticmethod
    def _coerce_scalar(text: str) -> Any:
        lowered = text.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text
