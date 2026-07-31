"""Incident record model — Git-history-like twin narrative."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class IncidentStep:
    at: str
    kind: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IncidentStep:
        return cls(
            at=str(data.get("at") or ""),
            kind=str(data.get("kind") or data.get("type") or "event"),
            summary=str(data.get("summary") or ""),
            payload=dict(data.get("payload") or {}),
        )


@dataclass
class IncidentRecord:
    api_version: str = "twinops.io/v1alpha1"
    kind: str = "TwinIncident"
    twin: str = ""
    started_at: str = ""
    ended_at: str = ""
    steps: list[IncidentStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": {
                "twin": self.twin,
                "startedAt": self.started_at,
                "endedAt": self.ended_at,
            },
            "spec": {"steps": [step.to_dict() for step in self.steps]},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IncidentRecord:
        meta = data.get("metadata") or {}
        spec = data.get("spec") or {}
        steps_raw = spec.get("steps") or data.get("steps") or []
        steps = [
            IncidentStep.from_dict(item)
            for item in steps_raw
            if isinstance(item, dict)
        ]
        return cls(
            api_version=str(data.get("apiVersion") or "twinops.io/v1alpha1"),
            kind=str(data.get("kind") or "TwinIncident"),
            twin=str(meta.get("twin") or data.get("twin") or ""),
            started_at=str(meta.get("startedAt") or ""),
            ended_at=str(meta.get("endedAt") or ""),
            steps=steps,
        )
