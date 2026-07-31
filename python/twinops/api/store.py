"""In-memory timeline and latest drift state for the live API."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TimelineEvent:
    id: int
    type: str
    timestamp: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "payload": self.payload,
        }


class TwinStore:
    def __init__(self, *, capacity: int = 200) -> None:
        self._lock = threading.RLock()
        self._timeline: deque[TimelineEvent] = deque(maxlen=capacity)
        self._seq = 0
        self.latest_drift: dict[str, Any] | None = None
        self.latest_observed: dict[str, Any] | None = None
        self.latest_proposal: dict[str, Any] | None = None
        self.twin_meta: dict[str, Any] = {}
        self.simulator_state: dict[str, Any] = {}

    def set_twin_meta(self, meta: dict[str, Any]) -> None:
        with self._lock:
            self.twin_meta = meta

    def record(
        self,
        *,
        event_type: str,
        timestamp: str,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> TimelineEvent:
        with self._lock:
            self._seq += 1
            event = TimelineEvent(
                id=self._seq,
                type=event_type,
                timestamp=timestamp,
                summary=summary,
                payload=payload or {},
            )
            self._timeline.appendleft(event)
            return event

    def set_drift(self, report: dict[str, Any]) -> None:
        with self._lock:
            self.latest_drift = report

    def set_observed(self, observed: dict[str, Any]) -> None:
        with self._lock:
            self.latest_observed = observed

    def set_simulator_state(self, state: dict[str, Any]) -> None:
        with self._lock:
            self.simulator_state = state

    def set_proposal(self, proposal: dict[str, Any]) -> None:
        with self._lock:
            self.latest_proposal = proposal

    def timeline(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._timeline)[: max(1, min(limit, 200))]
            return [item.to_dict() for item in items]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "twin": self.twin_meta,
                "simulator": self.simulator_state,
                "observed": self.latest_observed,
                "drift": self.latest_drift,
                "proposal": self.latest_proposal,
                "timeline": [item.to_dict() for item in list(self._timeline)[:50]],
            }
