"""MQTT telemetry reliability: ordering, dedupe, TTL stale, clock skew."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass
class AcceptResult:
    accepted: bool
    reason: str
    value: Any = None
    status: str = "OK"  # OK | STALE | UNKNOWN | CLOCK_SKEW
    sequence: int | None = None
    timestamp: datetime | None = None
    duplicate: bool = False
    out_of_order: bool = False
    clock_skew: bool = False


@dataclass
class SensorState:
    sensor_id: str
    value: Any = None
    sequence: int | None = None
    timestamp: datetime | None = None
    received_at: datetime | None = None
    status: str = "UNKNOWN"
    last_message_id: str | None = None
    epoch: str | None = None
    session_id: str | None = None
    sequence_resets: int = 0


@dataclass
class ReliabilityMetrics:
    received: int = 0
    accepted: int = 0
    duplicates_dropped: int = 0
    out_of_order_dropped: int = 0
    clock_skew_violations: int = 0
    stale_transitions: int = 0
    session_resumes: int = 0
    sequence_resets: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "received": self.received,
            "accepted": self.accepted,
            "duplicatesDropped": self.duplicates_dropped,
            "outOfOrderDropped": self.out_of_order_dropped,
            "clockSkewViolations": self.clock_skew_violations,
            "staleTransitions": self.stale_transitions,
            "sessionResumes": self.session_resumes,
            "sequenceResets": self.sequence_resets,
        }


@dataclass
class SensorTracker:
    """Per-sensor sequence/timestamp gate with dedupe window and TTL."""

    ttl_seconds: float = 30.0
    dedupe_window_seconds: float = 60.0
    max_skew_seconds: float = 30.0
    # Minimum backwards jump (exclusive) that may be treated as an epoch reset.
    sequence_reset_min_jump: int = 1
    max_sequence_resets: int = 8
    _sensors: dict[str, SensorState] = field(default_factory=dict)
    _recent_ids: dict[str, datetime] = field(default_factory=dict)
    metrics: ReliabilityMetrics = field(default_factory=ReliabilityMetrics)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def accept(
        self,
        sensor_id: str,
        value: Any,
        *,
        sequence: int | None = None,
        timestamp: Any = None,
        message_id: str | None = None,
        epoch: str | None = None,
        session_id: str | None = None,
        now: datetime | None = None,
    ) -> AcceptResult:
        now = now or datetime.now(UTC)
        ts = parse_timestamp(timestamp)
        with self._lock:
            self.metrics.received += 1
            self._prune_dedupe(now)

            # Clock skew: quarantine/reject WITHOUT advancing sequence/timestamp state.
            if ts is not None:
                skew = abs((now - ts).total_seconds())
                if skew > self.max_skew_seconds:
                    self.metrics.clock_skew_violations += 1
                    state = self._sensors.get(sensor_id)
                    return AcceptResult(
                        accepted=False,
                        reason="clock_skew",
                        clock_skew=True,
                        value=value,
                        status="CLOCK_SKEW",
                        sequence=sequence,
                        timestamp=ts,
                        out_of_order=False,
                    )

            if message_id:
                key = f"{sensor_id}:{message_id}"
                if key in self._recent_ids:
                    self.metrics.duplicates_dropped += 1
                    return AcceptResult(
                        accepted=False,
                        reason="duplicate",
                        duplicate=True,
                        value=value,
                        status="OK",
                    )
                self._recent_ids[key] = now

            state = self._sensors.get(sensor_id)
            reset_epoch = False
            if state is not None:
                if (
                    sequence is not None
                    and state.sequence is not None
                    and sequence < state.sequence
                ):
                    jump = state.sequence - sequence
                    marker = epoch or session_id
                    prev_marker = state.epoch or state.session_id
                    allow_reset = (
                        marker is not None
                        and marker != prev_marker
                        and jump >= self.sequence_reset_min_jump
                        and state.sequence_resets < self.max_sequence_resets
                    )
                    if allow_reset:
                        reset_epoch = True
                    else:
                        self.metrics.out_of_order_dropped += 1
                        return AcceptResult(
                            accepted=False,
                            reason="out_of_order_sequence",
                            out_of_order=True,
                            sequence=sequence,
                            timestamp=ts,
                            value=value,
                            status=state.status,
                        )
                if (
                    not reset_epoch
                    and sequence is None
                    and ts is not None
                    and state.timestamp is not None
                    and ts < state.timestamp
                ):
                    self.metrics.out_of_order_dropped += 1
                    return AcceptResult(
                        accepted=False,
                        reason="out_of_order_timestamp",
                        out_of_order=True,
                        sequence=sequence,
                        timestamp=ts,
                        value=value,
                        status=state.status,
                    )
                # Equal sequence with same message window → duplicate.
                if (
                    not reset_epoch
                    and sequence is not None
                    and state.sequence is not None
                    and sequence == state.sequence
                    and message_id is None
                ):
                    self.metrics.duplicates_dropped += 1
                    return AcceptResult(
                        accepted=False,
                        reason="duplicate_sequence",
                        duplicate=True,
                        sequence=sequence,
                        timestamp=ts,
                        value=value,
                        status=state.status,
                    )

            resets = state.sequence_resets if state else 0
            if reset_epoch:
                resets += 1
                self.metrics.sequence_resets += 1

            self._sensors[sensor_id] = SensorState(
                sensor_id=sensor_id,
                value=value,
                sequence=(
                    sequence
                    if sequence is not None
                    else (state.sequence if state else None)
                ),
                timestamp=ts or now,
                received_at=now,
                status="OK",
                last_message_id=message_id,
                epoch=epoch if epoch is not None else (state.epoch if state else None),
                session_id=(
                    session_id
                    if session_id is not None
                    else (state.session_id if state else None)
                ),
                sequence_resets=resets,
            )
            self.metrics.accepted += 1
            return AcceptResult(
                accepted=True,
                reason="epoch_reset" if reset_epoch else "ok",
                value=value,
                status="OK",
                sequence=sequence,
                timestamp=ts or now,
                clock_skew=False,
            )

    def refresh_stale(self, *, now: datetime | None = None) -> list[str]:
        """Mark sensors without fresh readings within TTL as STALE (never 'normal')."""
        now = now or datetime.now(UTC)
        stale: list[str] = []
        ttl = timedelta(seconds=self.ttl_seconds)
        with self._lock:
            for sensor_id, state in self._sensors.items():
                if state.received_at is None:
                    if state.status != "UNKNOWN":
                        state.status = "UNKNOWN"
                        state.value = "UNKNOWN"
                        stale.append(sensor_id)
                    continue
                if now - state.received_at > ttl and state.status not in {"STALE", "UNKNOWN"}:
                    state.status = "STALE"
                    # Never leave a stale sensor reporting a normal/running value.
                    if isinstance(state.value, str) and state.value.lower() in {
                        "normal",
                        "running",
                        "ok",
                        "healthy",
                    }:
                        state.value = "STALE"
                    self.metrics.stale_transitions += 1
                    stale.append(sensor_id)
                elif now - state.received_at > ttl and state.status == "STALE":
                    stale.append(sensor_id)
        return stale

    def snapshot(self) -> dict[str, SensorState]:
        with self._lock:
            return {
                sid: SensorState(
                    sensor_id=s.sensor_id,
                    value=s.value,
                    sequence=s.sequence,
                    timestamp=s.timestamp,
                    received_at=s.received_at,
                    status=s.status,
                    last_message_id=s.last_message_id,
                    epoch=s.epoch,
                    session_id=s.session_id,
                    sequence_resets=s.sequence_resets,
                )
                for sid, s in self._sensors.items()
            }

    def status(self) -> dict[str, Any]:
        with self._lock:
            sensors = {
                sid: {
                    "value": s.value,
                    "sequence": s.sequence,
                    "timestamp": s.timestamp.isoformat().replace("+00:00", "Z")
                    if s.timestamp
                    else None,
                    "receivedAt": s.received_at.isoformat().replace("+00:00", "Z")
                    if s.received_at
                    else None,
                    "status": s.status,
                }
                for sid, s in self._sensors.items()
            }
            stale = sum(1 for s in self._sensors.values() if s.status == "STALE")
            unknown = sum(1 for s in self._sensors.values() if s.status == "UNKNOWN")
            skew = sum(1 for s in self._sensors.values() if s.status == "CLOCK_SKEW")
            return {
                "sensors": sensors,
                "staleSensors": stale,
                "unknownSensors": unknown,
                "clockSkewSensors": skew,
                "metrics": self.metrics.to_dict(),
            }

    def note_session_resume(self) -> None:
        with self._lock:
            self.metrics.session_resumes += 1

    def _prune_dedupe(self, now: datetime) -> None:
        window = timedelta(seconds=self.dedupe_window_seconds)
        expired = [key for key, ts in self._recent_ids.items() if now - ts > window]
        for key in expired:
            del self._recent_ids[key]
