"""Validate TwinOps MQTT telemetry payloads (twinops.mqtt.payload.v1)."""

from __future__ import annotations

from typing import Any

REQUIRED_FIELDS = ("schema", "topic", "value", "timestamp")
SCHEMA_NAME = "twinops.mqtt.payload.v1"


def validate_mqtt_payload(payload: dict[str, Any]) -> list[str]:
    """Return a list of validation errors (empty means ok)."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload must be an object"]
    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"missing required field: {field}")
    schema = payload.get("schema")
    if schema is not None and schema != SCHEMA_NAME:
        errors.append(f"unsupported schema: {schema!r} (expected {SCHEMA_NAME!r})")
    topic = payload.get("topic")
    if topic is not None and (not isinstance(topic, str) or not topic.strip()):
        errors.append("topic must be a non-empty string")
    timestamp = payload.get("timestamp")
    if timestamp is not None and (not isinstance(timestamp, str) or not timestamp.strip()):
        errors.append("timestamp must be a non-empty string")
    return errors


def assert_valid_mqtt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    errors = validate_mqtt_payload(payload)
    if errors:
        raise ValueError("; ".join(errors))
    return payload
