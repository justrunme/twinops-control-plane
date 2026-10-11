"""MQTT telemetry reliability: OOO, dedupe, stale TTL, clock skew, drift STALE."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from twinops.drift.engine import detect_drift
from twinops.drift.model import DesiredResource, DesiredState, ObservedState
from twinops.telemetry.ingest import ObservationIngest, TopicBinding
from twinops.telemetry.reliability import SensorTracker


def _binding() -> list[TopicBinding]:
    return [
        TopicBinding(
            topic="factory/robot-01/temperature",
            prim="/World/Factory/LineA/Robot01",
            attribute="twinops:temperature",
        ),
        TopicBinding(
            topic="factory/robot-01/status",
            prim="/World/Factory/LineA/Robot01",
            attribute="twinops:status",
        ),
    ]


def test_out_of_order_sequence_dropped() -> None:
    ingest = ObservationIngest(_binding(), ttl_seconds=60)
    assert ingest.handle_message(
        "factory/robot-01/temperature",
        b'{"value": 50, "sequence": 5, "source": "plc", "timestamp": "2026-10-11T10:00:05Z"}',
    )
    assert (
        ingest.handle_message(
            "factory/robot-01/temperature",
            b'{"value": 40, "sequence": 3, "source": "plc", "timestamp": "2026-10-11T10:00:03Z"}',
        )
        is False
    )
    assert ingest.out_of_order_dropped == 1
    assert ingest.last_value == 50


def test_out_of_order_timestamp_dropped() -> None:
    ingest = ObservationIngest(_binding(), ttl_seconds=60)
    assert ingest.handle_message(
        "factory/robot-01/temperature",
        b'{"value": 50, "source": "plc", "timestamp": "2026-10-11T10:00:05Z"}',
    )
    assert (
        ingest.handle_message(
            "factory/robot-01/temperature",
            b'{"value": 40, "source": "plc", "timestamp": "2026-10-11T10:00:01Z"}',
        )
        is False
    )
    assert ingest.out_of_order_dropped == 1


def test_duplicate_message_id_dropped() -> None:
    ingest = ObservationIngest(_binding(), dedupe_window_seconds=60)
    payload = (
        b'{"value": 55, "source": "plc", "messageId": "m-1",'
        b' "timestamp": "2026-10-11T10:00:00Z", "sequence": 1}'
    )
    assert ingest.handle_message("factory/robot-01/temperature", payload)
    assert ingest.handle_message("factory/robot-01/temperature", payload) is False
    assert ingest.duplicates_dropped == 1


def test_stale_sensor_never_normal() -> None:
    tracker = SensorTracker(ttl_seconds=0.01)
    ingest = ObservationIngest(_binding(), tracker=tracker)
    assert ingest.handle_message(
        "factory/robot-01/status",
        b'{"value": "running", "source": "plc", '
        b'"timestamp": "2026-10-11T10:00:00Z", "sequence": 1}',
    )
    # Force received_at into the past.
    state = tracker._sensors["factory/robot-01/status"]
    state.received_at = datetime.now(UTC) - timedelta(seconds=5)
    stale = ingest.apply_stale()
    assert "factory/robot-01/status" in stale
    merged = ingest.merge_observations(
        {
            "timestamp": "t",
            "source": "base",
            "observations": [
                {
                    "prim": "/World/Factory/LineA/Robot01",
                    "attributes": {"twinops:status": "running"},
                }
            ],
        }
    )
    attrs = merged["observations"][0]["attributes"]
    assert attrs["twinops:status"] == "STALE"
    assert attrs["twinops:telemetryStatus"] == "STALE"
    assert attrs["twinops:status"] != "running"


def test_clock_skew_flagged() -> None:
    ingest = ObservationIngest(_binding(), max_skew_seconds=5)
    far = (datetime.now(UTC) + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    assert ingest.handle_message(
        "factory/robot-01/temperature",
        f'{{"value": 60, "source": "plc", "timestamp": "{far}", "sequence": 1}}'.encode(),
    )
    assert ingest.clock_skew_violations == 1
    status = ingest.status()
    assert status["reliability"]["clockSkewSensors"] >= 1
    assert any(
        c["type"] == "TelemetryClockSkew" and c["status"] == "True"
        for c in status["conditions"]
    )


def test_drift_treats_stale_as_not_synced() -> None:
    desired = DesiredState(
        name="t",
        resources=[
            DesiredResource(
                prim="/World/Factory/LineA/Robot01",
                attributes={"twinops:status": "running", "twinops:temperature": 42},
            )
        ],
    )
    observed = ObservedState(
        timestamp="t",
        source="mqtt",
        attributes_by_prim={
            "/World/Factory/LineA/Robot01": {
                "twinops:status": "STALE",
                "twinops:temperature": 42,
                "twinops:telemetryStatus": "STALE",
            }
        },
    )
    report = detect_drift(desired=desired, stage={}, observed=observed)
    assert report.has_drift
    statuses = {f.status for f in report.findings}
    assert "STALE" in statuses
    assert not any(
        f.status == "SYNCED" and f.attribute == "twinops:status" for f in report.findings
    )


def test_session_resume_metric_hook() -> None:
    tracker = SensorTracker()
    tracker.note_session_resume()
    assert tracker.metrics.session_resumes == 1
