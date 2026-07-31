"""MQTT payload schema helper tests."""

from __future__ import annotations

import pytest
from twinops.telemetry.payload import assert_valid_mqtt_payload, validate_mqtt_payload


def test_validate_mqtt_payload_ok() -> None:
    payload = {
        "schema": "twinops.mqtt.payload.v1",
        "topic": "factory/robot-01/temperature",
        "value": 42.0,
        "timestamp": "2026-07-31T10:00:00Z",
        "source": "plc",
    }
    assert validate_mqtt_payload(payload) == []
    assert assert_valid_mqtt_payload(payload)["topic"].startswith("factory/")


def test_validate_mqtt_payload_errors() -> None:
    errors = validate_mqtt_payload({"schema": "other"})
    assert any("missing required field" in err for err in errors)
    with pytest.raises(ValueError):
        assert_valid_mqtt_payload({"schema": "other"})
