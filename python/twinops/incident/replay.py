"""Replay a TwinIncident against offline drift inputs (demo narrative)."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from twinops.drift.engine import detect_drift
from twinops.incident.model import IncidentRecord, IncidentStep
from twinops.incident.record import load_incident

ROBOT_PRIM = "/World/Factory/LineA/Robot01"


@dataclass
class ReplayResult:
    twin: str
    steps_played: int
    ticks: list[dict[str, Any]] = field(default_factory=list)
    verified: bool | None = None
    verify_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "twin": self.twin,
            "stepsPlayed": self.steps_played,
            "ticks": self.ticks,
        }
        if self.verified is not None:
            payload["verified"] = self.verified
            payload["verifyErrors"] = self.verify_errors
        return payload


def _apply_live_state(observed: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Map live simulator state payload into observed Robot01 attributes."""
    attrs: dict[str, Any] = {}
    if "robot_temp" in state:
        attrs["twinops:temperature"] = state["robot_temp"]
    if "robot_status" in state:
        attrs["twinops:status"] = state["robot_status"]
    if "robot_firmware" in state:
        attrs["twinops:firmware"] = state["robot_firmware"]
    if not attrs:
        return observed
    observations = list(observed.get("observations") or [])
    found = False
    for item in observations:
        if str(item.get("prim")) == ROBOT_PRIM:
            existing = dict(item.get("attributes") or {})
            existing.update(attrs)
            item["attributes"] = existing
            found = True
            break
    if not found:
        observations.append({"prim": ROBOT_PRIM, "attributes": attrs})
    observed["observations"] = observations
    return observed


def _observed_from_step(step: IncidentStep, base_observed: dict[str, Any]) -> dict[str, Any]:
    """Merge step payload observations into a copy of base observed JSON."""
    observed = copy.deepcopy(base_observed)
    payload = step.payload
    if isinstance(payload.get("observed"), dict):
        return payload["observed"]
    if isinstance(payload.get("state"), dict):
        return _apply_live_state(observed, payload["state"])
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


def _verify_result(record: IncidentRecord, ticks: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not ticks:
        return False, ["no ticks to verify"]
    final = ticks[-1]
    expected_state = (record.expected_final_state or "").upper()
    if expected_state in {"SYNCED", "OK", "HEALTHY"}:
        if final.get("hasDrift"):
            errors.append(
                f"expectedFinalState={expected_state} but final hasDrift=true "
                f"counts={final.get('counts')}"
            )
    elif expected_state == "RECOVERED":
        # Spike narrative healed: no CRITICAL; residual PLM MISSING/DRIFT may remain
        # on offline sample stages.
        critical = int((final.get("counts") or {}).get("CRITICAL") or 0)
        if critical != 0:
            errors.append(f"expectedFinalState=RECOVERED but CRITICAL={critical}")
    elif expected_state in {"DRIFT", "CRITICAL", "WARNING"}:
        if not final.get("hasDrift"):
            errors.append(f"expectedFinalState={expected_state} but final hasDrift=false")
    if record.expected_critical_drifts is not None:
        critical = int((final.get("counts") or {}).get("CRITICAL") or 0)
        if critical != record.expected_critical_drifts:
            errors.append(
                f"expectedCriticalDrifts={record.expected_critical_drifts} "
                f"got={critical}"
            )
    if not expected_state and record.expected_critical_drifts is None:
        errors.append("incident has no status.expectedFinalState / expectedCriticalDrifts")
    return (not errors), errors


def replay_incident(
    incident: IncidentRecord | str | Path,
    *,
    desired: str | Path,
    stage: str | Path,
    observed: str | Path,
    manifest: str | Path | None = None,
    verify: bool = False,
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
        if step.kind in {
            "telemetry",
            "drift",
            "spike",
            "event",
            "highlight",
            "proposal",
            "reconcile",
        }:
            current = _observed_from_step(step, current)
        report = detect_drift(
            desired=desired,
            stage=stage,
            observed=current,
            manifest=manifest,
        )
        ticks.append(
            {
                "at": step.at,
                "kind": step.kind,
                "summary": step.summary,
                "hasDrift": report.has_drift,
                "counts": dict(report.summary),
                "transition": (
                    "CRITICAL"
                    if int(report.summary.get("CRITICAL") or 0)
                    else ("DRIFT" if report.has_drift else "SYNCED")
                ),
            }
        )
    result = ReplayResult(
        twin=record.twin,
        steps_played=len(record.steps),
        ticks=ticks,
    )
    if verify:
        ok, errors = _verify_result(record, ticks)
        result.verified = ok
        result.verify_errors = errors
    return result


def json_load(path: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(path, dict):
        return path
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("observed JSON must be an object")
    return data
