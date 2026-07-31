"""Replay a TwinIncident against offline drift inputs (demo narrative)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from twinops.drift.engine import detect_drift
from twinops.incident.model import IncidentRecord, IncidentStep
from twinops.incident.record import load_incident


@dataclass
class ReplayResult:
    twin: str
    steps_played: int
    ticks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "twin": self.twin,
            "stepsPlayed": self.steps_played,
            "ticks": self.ticks,
        }


def _observed_from_step(step: IncidentStep, base_observed: dict[str, Any]) -> dict[str, Any]:
    """Merge step payload observations into a copy of base observed JSON."""
    import copy

    observed = copy.deepcopy(base_observed)
    payload = step.payload
    # Live timeline drift events often embed report status; prefer explicit observed.
    if isinstance(payload.get("observed"), dict):
        return payload["observed"]
    fragment = payload.get("observations") or payload.get("observation")
    if isinstance(fragment, list):
        observations = list(observed.get("observations") or [])
        by_prim = {
            str(item.get("prim")): item
            for item in observations
            if isinstance(item, dict)
        }
        for item in fragment:
            if not isinstance(item, dict):
                continue
            prim = str(item.get("prim") or "")
            attrs = dict(item.get("attributes") or {})
            if prim in by_prim:
                existing = dict(by_prim[prim].get("attributes") or {})
                existing.update(attrs)
                by_prim[prim]["attributes"] = existing
            else:
                by_prim[prim] = {"prim": prim, "attributes": attrs}
        observed["observations"] = list(by_prim.values())
        return observed
    # Spike-style payload: {prim, attribute, value}
    prim = payload.get("prim")
    attribute = payload.get("attribute")
    if prim and attribute and "value" in payload:
        observations = list(observed.get("observations") or [])
        found = False
        for item in observations:
            if str(item.get("prim")) == str(prim):
                attrs = dict(item.get("attributes") or {})
                attrs[str(attribute)] = payload["value"]
                item["attributes"] = attrs
                found = True
                break
        if not found:
            observations.append(
                {
                    "prim": str(prim),
                    "attributes": {str(attribute): payload["value"]},
                }
            )
        observed["observations"] = observations
    return observed


def replay_incident(
    incident: IncidentRecord | str | Path,
    *,
    desired: str | Path,
    stage: str | Path,
    observed: str | Path,
    manifest: str | Path | None = None,
) -> ReplayResult:
    """Re-run drift for each incident step that carries observation deltas."""
    record = (
        incident
        if isinstance(incident, IncidentRecord)
        else load_incident(incident)
    )
    base_observed = json_load(observed)
    ticks: list[dict[str, Any]] = []
    current = base_observed
    for step in record.steps:
        if step.kind in {"telemetry", "drift", "spike", "event"}:
            current = _observed_from_step(step, current)
        report = detect_drift(
            desired=desired,
            stage=stage,
            observed=current,  # dict accepted by load_observed_state
            manifest=manifest,
        )
        ticks.append(
            {
                "at": step.at,
                "kind": step.kind,
                "summary": step.summary,
                "hasDrift": report.has_drift,
                "counts": dict(report.summary),
            }
        )
    return ReplayResult(
        twin=record.twin,
        steps_played=len(record.steps),
        ticks=ticks,
    )


def json_load(path: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(path, dict):
        return path
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("observed JSON must be an object")
    return data
