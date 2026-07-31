"""SQLite persistence for TwinStore (reference-architecture control-plane state)."""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from twinops.api.store import TimelineEvent, TwinStore


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class PersistentTwinStore(TwinStore):
    """TwinStore that mirrors key state into SQLite and reloads on start."""

    def __init__(self, db_path: str | Path, *, capacity: int = 200) -> None:
        super().__init__(capacity=capacity)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._load()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS timeline (
                  id INTEGER PRIMARY KEY,
                  type TEXT NOT NULL,
                  timestamp TEXT NOT NULL,
                  summary TEXT NOT NULL,
                  payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  at TEXT NOT NULL,
                  action TEXT NOT NULL,
                  detail TEXT NOT NULL
                );
                """
            )

    def _set_meta(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )

    def _get_meta(self, key: str) -> Any | None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["value"])

    def _audit(self, action: str, detail: dict[str, Any] | None = None) -> None:
        self._conn.execute(
            "INSERT INTO audit_events(at, action, detail) VALUES (?, ?, ?)",
            (_utcnow(), action, json.dumps(detail or {})),
        )

    def _load(self) -> None:
        with self._lock:
            twin = self._get_meta("twin_meta")
            if isinstance(twin, dict):
                self.twin_meta = twin
            drift = self._get_meta("latest_drift")
            if isinstance(drift, dict):
                self.latest_drift = drift
            observed = self._get_meta("latest_observed")
            if isinstance(observed, dict):
                self.latest_observed = observed
            proposal = self._get_meta("latest_proposal")
            if isinstance(proposal, dict):
                self.latest_proposal = proposal
            sim = self._get_meta("simulator_state")
            if isinstance(sim, dict):
                self.simulator_state = sim
            seq = self._get_meta("seq")
            if isinstance(seq, int):
                self._seq = seq
            rows = self._conn.execute(
                "SELECT id, type, timestamp, summary, payload "
                "FROM timeline ORDER BY id DESC LIMIT ?",
                (self._timeline.maxlen or 200,),
            ).fetchall()
            events = [
                TimelineEvent(
                    id=int(row["id"]),
                    type=str(row["type"]),
                    timestamp=str(row["timestamp"]),
                    summary=str(row["summary"]),
                    payload=json.loads(row["payload"]),
                )
                for row in rows
            ]
            self._timeline = deque(events, maxlen=self._timeline.maxlen)

    def set_twin_meta(self, meta: dict[str, Any]) -> None:
        super().set_twin_meta(meta)
        with self._lock:
            with self._conn:
                self._set_meta("twin_meta", meta)
                self._audit("twin_meta", {"name": meta.get("name")})

    def record(
        self,
        *,
        event_type: str,
        timestamp: str,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> TimelineEvent:
        event = super().record(
            event_type=event_type,
            timestamp=timestamp,
            summary=summary,
            payload=payload,
        )
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO timeline"
                    "(id, type, timestamp, summary, payload) VALUES (?, ?, ?, ?, ?)",
                    (
                        event.id,
                        event.type,
                        event.timestamp,
                        event.summary,
                        json.dumps(event.payload),
                    ),
                )
                self._set_meta("seq", self._seq)
                self._audit(
                    "timeline",
                    {"id": event.id, "type": event.type, "summary": event.summary},
                )
                # Keep table bounded roughly to capacity.
                cutoff = max(0, self._seq - (self._timeline.maxlen or 200))
                if cutoff:
                    self._conn.execute("DELETE FROM timeline WHERE id <= ?", (cutoff,))
        return event

    def set_drift(self, report: dict[str, Any]) -> None:
        super().set_drift(report)
        with self._lock:
            with self._conn:
                self._set_meta("latest_drift", report)
                scene_hash = None
                status = report.get("status") or {}
                scene_hash = status.get("sceneHash") or status.get("stageHash")
                if scene_hash:
                    twin = dict(self.twin_meta)
                    twin["sceneHash"] = scene_hash
                    self.twin_meta = twin
                    self._set_meta("twin_meta", twin)
                self._audit("drift", {"hasDrift": (status.get("hasDrift"))})

    def set_observed(self, observed: dict[str, Any]) -> None:
        super().set_observed(observed)
        with self._lock:
            with self._conn:
                self._set_meta("latest_observed", observed)

    def set_simulator_state(self, state: dict[str, Any]) -> None:
        super().set_simulator_state(state)
        with self._lock:
            with self._conn:
                self._set_meta("simulator_state", state)

    def set_proposal(self, proposal: dict[str, Any]) -> None:
        super().set_proposal(proposal)
        with self._lock:
            with self._conn:
                self._set_meta("latest_proposal", proposal)
                status = proposal.get("status") or {}
                self._audit(
                    "proposal",
                    {
                        "applied": status.get("applied"),
                        "changes": len(proposal.get("changes") or []),
                    },
                )

    def audit_trail(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, at, action, detail FROM audit_events "
                "ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
            return [
                {
                    "id": int(row["id"]),
                    "at": row["at"],
                    "action": row["action"],
                    "detail": json.loads(row["detail"]),
                }
                for row in rows
            ]


def create_store(
    *,
    capacity: int = 200,
    db_path: str | Path | None = None,
) -> TwinStore:
    if db_path:
        return PersistentTwinStore(db_path, capacity=capacity)
    return TwinStore(capacity=capacity)
