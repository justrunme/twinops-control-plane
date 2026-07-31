"""Shared drift data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STATUS_ORDER = {
    "SYNCED": 0,
    "WARNING": 1,
    "MISSING": 2,
    "DRIFT": 3,
    "CRITICAL": 4,
}


@dataclass(frozen=True)
class DesiredResource:
    prim: str
    attributes: dict[str, Any]


@dataclass
class DesiredState:
    name: str
    resources: list[DesiredResource] = field(default_factory=list)

    def by_prim(self) -> dict[str, DesiredResource]:
        return {item.prim: item for item in self.resources}


@dataclass
class ObservedState:
    timestamp: str | None
    source: str | None
    attributes_by_prim: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class DriftFinding:
    prim: str
    attribute: str
    desired: Any
    rendered: Any
    observed: Any
    status: str
    severity: str
    message: str

    @property
    def short_prim(self) -> str:
        return self.prim.rsplit("/", 1)[-1]


@dataclass
class PolicyThreshold:
    prim: str
    attribute: str
    warn_above: float | None = None
    critical_above: float | None = None


def normalize_attr(name: str) -> str:
    if name.startswith("twinops:"):
        return name
    mapping = {
        "plmRevision": "twinops:plmRevision",
        "plmItemId": "twinops:plmItemId",
        "lifecycle": "twinops:lifecycle",
        "firmware": "twinops:firmware",
        "status": "twinops:status",
        "temperature": "twinops:temperature",
        "speed": "twinops:speed",
    }
    return mapping.get(name, f"twinops:{name}")


def display_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return text if text else "0"
    return str(value)
