"""MQTT → observed-state ingest for TwinOps live demos."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any

from twinops.telemetry.bus import TelemetryBus

logger = logging.getLogger(__name__)

IGNORE_SOURCES = frozenset({"twinops", "twinops-bus", "twinops-simulator"})


@dataclass(frozen=True)
class TopicBinding:
    topic: str
    prim: str
    attribute: str


class ObservationIngest:
    """Maps inbound MQTT topics onto observed twin attributes."""

    def __init__(self, bindings: list[TopicBinding] | None = None) -> None:
        self._bindings = {item.topic: item for item in (bindings or [])}
        self._overrides: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self.received = 0
        self.ignored = 0
        self.last_topic: str | None = None
        self.last_value: Any = None

    @classmethod
    def from_manifest_mappings(cls, mappings: list[Any]) -> ObservationIngest:
        bindings = [
            TopicBinding(
                topic=str(item.topic),
                prim=str(item.prim),
                attribute=str(item.attribute),
            )
            for item in mappings
            if getattr(item, "topic", None) and getattr(item, "prim", None)
        ]
        return cls(bindings)

    @property
    def topics(self) -> list[str]:
        return sorted(self._bindings)

    def binding_for(self, topic: str) -> TopicBinding | None:
        return self._bindings.get(topic)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": True,
                "topics": self.topics,
                "received": self.received,
                "ignored": self.ignored,
                "lastTopic": self.last_topic,
                "lastValue": self.last_value,
                "overridePrims": sorted(self._overrides),
            }

    def handle_message(self, topic: str, payload: bytes | str) -> bool:
        """Apply one MQTT message. Returns True when an override was stored."""
        binding = self._bindings.get(topic)
        if binding is None:
            with self._lock:
                self.ignored += 1
            return False

        raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        value, source = self._parse_payload(raw)
        if source in IGNORE_SOURCES:
            with self._lock:
                self.ignored += 1
            return False

        with self._lock:
            self._overrides.setdefault(binding.prim, {})[binding.attribute] = value
            self.received += 1
            self.last_topic = topic
            self.last_value = value
        logger.info(
            "mqtt ingest %s → %s.%s = %r",
            topic,
            binding.prim,
            binding.attribute,
            value,
        )
        return True

    def merge_observations(self, observed_raw: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of observed_raw with MQTT overrides applied."""
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

    @staticmethod
    def _parse_payload(raw: str) -> tuple[Any, str | None]:
        text = raw.strip()
        if not text:
            return None, None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return ObservationIngest._coerce_scalar(text), None
        if isinstance(data, dict):
            source = data.get("source")
            if "value" in data:
                return data["value"], str(source) if source is not None else None
            return data, str(source) if source is not None else None
        return data, None

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
