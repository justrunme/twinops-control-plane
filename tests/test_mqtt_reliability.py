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
    ingest = ObservationIngest(_binding(), ttl_seconds=60, max_skew_seconds=3600)
    now = datetime.now(UTC)
    t5 = (now + timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    t3 = (now + timedelta(seconds=3)).isoformat().replace("+00:00", "Z")
    assert ingest.handle_message(
        "factory/robot-01/temperature",
        f'{{"value": 50, "sequence": 5, "source": "plc", "timestamp": "{t5}"}}'.encode(),
    )
    assert (
        ingest.handle_message(
            "factory/robot-01/temperature",
            f'{{"value": 40, "sequence": 3, "source": "plc", "timestamp": "{t3}"}}'.encode(),
        )
        is False
    )
    assert ingest.out_of_order_dropped == 1
    assert ingest.last_value == 50


def test_out_of_order_timestamp_dropped() -> None:
    ingest = ObservationIngest(_binding(), ttl_seconds=60, max_skew_seconds=3600)
    now = datetime.now(UTC)
    t5 = (now + timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    t1 = (now + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    assert ingest.handle_message(
        "factory/robot-01/temperature",
        f'{{"value": 50, "source": "plc", "timestamp": "{t5}"}}'.encode(),
    )
    assert (
        ingest.handle_message(
            "factory/robot-01/temperature",
            f'{{"value": 40, "source": "plc", "timestamp": "{t1}"}}'.encode(),
        )
        is False
    )
    assert ingest.out_of_order_dropped == 1


def test_duplicate_message_id_dropped() -> None:
    ingest = ObservationIngest(_binding(), dedupe_window_seconds=60, max_skew_seconds=3600)
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    payload = (
        f'{{"value": 55, "source": "plc", "messageId": "m-1",'
        f' "timestamp": "{ts}", "sequence": 1}}'
    ).encode()
    assert ingest.handle_message("factory/robot-01/temperature", payload)
    assert ingest.handle_message("factory/robot-01/temperature", payload) is False
    assert ingest.duplicates_dropped == 1


def test_stale_sensor_never_normal() -> None:
    import time

    tracker = SensorTracker(ttl_seconds=0.05, max_skew_seconds=3600)
    ingest = ObservationIngest(_binding(), tracker=tracker)
    now = datetime.now(UTC)
    ts = now.isoformat().replace("+00:00", "Z")
    assert ingest.handle_message(
        "factory/robot-01/status",
        f'{{"value": "running", "source": "plc", "timestamp": "{ts}", "sequence": 1}}'.encode(),
    )
    time.sleep(0.12)
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


def test_clock_skew_rejected_without_advancing_state() -> None:
    tracker = SensorTracker(max_skew_seconds=5)
    ingest = ObservationIngest(_binding(), tracker=tracker)
    now = datetime.now(UTC)
    ok_ts = now.isoformat().replace("+00:00", "Z")
    assert ingest.handle_message(
        "factory/robot-01/temperature",
        f'{{"value": 50, "source": "plc", "timestamp": "{ok_ts}", "sequence": 2}}'.encode(),
    )
    far = (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    assert (
        ingest.handle_message(
            "factory/robot-01/temperature",
            f'{{"value": 99, "source": "plc", "timestamp": "{far}", "sequence": 99}}'.encode(),
        )
        is False
    )
    assert ingest.clock_skew_violations == 1
    # Far-future must not advance sequence — later in-order message still accepted.
    later = (now + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    assert ingest.handle_message(
        "factory/robot-01/temperature",
        f'{{"value": 55, "source": "plc", "timestamp": "{later}", "sequence": 3}}'.encode(),
    )
    assert ingest.last_value == 55
    assert tracker.snapshot()["factory/robot-01/temperature"].sequence == 3


def test_sequence_epoch_reset_bounded() -> None:
    tracker = SensorTracker(max_skew_seconds=3600)
    now = datetime.now(UTC)
    ts = now.isoformat().replace("+00:00", "Z")
    assert tracker.accept("s1", 1, sequence=100, timestamp=ts, epoch="e1", now=now).accepted
    # Backwards without new epoch → reject
    r = tracker.accept("s1", 2, sequence=1, timestamp=ts, epoch="e1", now=now)
    assert not r.accepted and r.out_of_order
    # New epoch + backwards jump → reset
    r2 = tracker.accept("s1", 3, sequence=1, timestamp=ts, epoch="e2", now=now)
    assert r2.accepted and r2.reason == "epoch_reset"
    assert tracker.metrics.sequence_resets == 1
    # Bound resets
    tracker.max_sequence_resets = 1
    r3 = tracker.accept("s1", 4, sequence=0, timestamp=ts, epoch="e3", now=now)
    assert not r3.accepted and r3.out_of_order


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
