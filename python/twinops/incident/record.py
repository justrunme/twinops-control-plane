"""Export live timeline into a TwinIncident record."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from twinops.incident.model import IncidentRecord, IncidentStep


def timeline_to_incident(
    timeline: list[dict[str, Any]],
    *,
    twin: str = "",
    expected_final_state: str = "",
    expected_critical_drifts: int | None = None,
) -> IncidentRecord:
    """Build an incident from newest-first or oldest-first timeline events."""
    events = list(timeline)
    # Normalize to chronological order.
    def _ts(item: dict[str, Any]) -> str:
        return str(item.get("timestamp") or item.get("at") or "")

    chronological = sorted(events, key=_ts)
    steps = [
        IncidentStep(
            at=_ts(item),
            kind=str(item.get("type") or item.get("kind") or "event"),
            summary=str(item.get("summary") or ""),
            payload=dict(item.get("payload") or {}),
        )
        for item in chronological
    ]
    started = steps[0].at if steps else ""
    ended = steps[-1].at if steps else ""
    final_state = expected_final_state
    critical = expected_critical_drifts
    if not final_state:
        for step in reversed(steps):
            payload = step.payload
            if "hasDrift" in payload:
                final_state = "DRIFT" if payload.get("hasDrift") else "SYNCED"
                summary = payload.get("summary") or {}
                if isinstance(summary, dict) and critical is None:
                    critical = int(summary.get("CRITICAL") or 0)
                break
    return IncidentRecord(
        twin=twin,
        started_at=started,
        ended_at=ended,
        steps=steps,
        expected_final_state=final_state,
        expected_critical_drifts=critical,
    )


def export_incident(
    timeline: list[dict[str, Any]],
    path: str | Path,
    *,
    twin: str = "",
) -> IncidentRecord:
    record = timeline_to_incident(timeline, twin=twin)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8")
    return record


def load_incident(path: str | Path) -> IncidentRecord:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("incident JSON must be an object")
    return IncidentRecord.from_dict(data)
