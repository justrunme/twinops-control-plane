"""Session-layer highlight state machine (source assets stay untouched)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RuntimeState(str, Enum):
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    STALE = "stale"
    INVALID_PRIM = "invalid_prim"
    INVALID_PAYLOAD = "invalid_payload"
    HIGHLIGHT_APPLIED = "highlight_applied"
    HIGHLIGHT_CLEARED = "highlight_cleared"


@dataclass(frozen=True)
class SessionOverride:
    prim: str
    color: tuple[float, float, float]
    intensity: float
    status: str


@dataclass
class SessionHighlightLayer:
    """In-memory session overrides — never writes source USDA files."""

    overrides: dict[str, SessionOverride] = field(default_factory=dict)
    state: RuntimeState = RuntimeState.CONNECTED
    notes: list[str] = field(default_factory=list)
    source_path: str | None = None
    _fingerprint: str = ""

    def mark_connected(self) -> None:
        self.state = RuntimeState.CONNECTED

    def mark_reconnecting(self) -> None:
        self.state = RuntimeState.RECONNECTING

    def mark_stale(self) -> None:
        self.state = RuntimeState.STALE

    def apply(
        self,
        targets: list[dict[str, Any]],
        *,
        valid_prims: set[str] | None = None,
    ) -> list[str]:
        """Apply highlight targets idempotently into the session layer."""
        self.notes = []
        if not isinstance(targets, list):
            self.state = RuntimeState.INVALID_PAYLOAD
            self.notes.append("invalid payload: targets must be a list")
            return list(self.notes)

        fingerprint = self._targets_fingerprint(targets)
        if fingerprint == self._fingerprint and self.overrides:
            self.state = RuntimeState.HIGHLIGHT_APPLIED
            self.notes.append("idempotent — session overrides unchanged")
            return list(self.notes)

        next_overrides: dict[str, SessionOverride] = {}
        for raw in targets:
            if not isinstance(raw, dict):
                self.state = RuntimeState.INVALID_PAYLOAD
                self.notes.append("invalid payload: target is not an object")
                continue
            prim = str(raw.get("prim") or "")
            if not prim:
                self.state = RuntimeState.INVALID_PAYLOAD
                self.notes.append("invalid payload: missing prim")
                continue
            if valid_prims is not None and prim not in valid_prims:
                self.state = RuntimeState.INVALID_PRIM
                self.notes.append(f"invalid prim: {prim}")
                continue
            color_raw = raw.get("color") or [0.86, 0.15, 0.15]
            try:
                color = (
                    float(color_raw[0]),
                    float(color_raw[1]),
                    float(color_raw[2]),
                )
                intensity = float(raw.get("intensity") or 0.8)
            except (TypeError, ValueError, IndexError):
                self.state = RuntimeState.INVALID_PAYLOAD
                self.notes.append(f"invalid payload for {prim}")
                continue
            next_overrides[prim] = SessionOverride(
                prim=prim,
                color=color,
                intensity=intensity,
                status=str(raw.get("status") or "DRIFT"),
            )
            self.notes.append(f"SESSION SET {prim}")

        self.overrides = next_overrides
        self._fingerprint = fingerprint
        if next_overrides and self.state not in {
            RuntimeState.INVALID_PRIM,
            RuntimeState.INVALID_PAYLOAD,
        }:
            self.state = RuntimeState.HIGHLIGHT_APPLIED
        elif not next_overrides and self.state not in {
            RuntimeState.INVALID_PRIM,
            RuntimeState.INVALID_PAYLOAD,
        }:
            self.state = RuntimeState.HIGHLIGHT_CLEARED
            self.notes.append("SESSION CLEAR")
        return list(self.notes)

    def clear(self) -> list[str]:
        self.overrides = {}
        self._fingerprint = ""
        self.state = RuntimeState.HIGHLIGHT_CLEARED
        self.notes = ["SESSION CLEAR"]
        return list(self.notes)

    def restore_after_reconnect(self) -> list[str]:
        """Re-assert current session overrides after a reconnect."""
        self.state = RuntimeState.RECONNECTING
        if not self.overrides:
            self.state = RuntimeState.CONNECTED
            return ["reconnect — no session overrides to restore"]
        notes = [
            f"reconnect restore {override.prim}"
            for override in self.overrides.values()
        ]
        self.state = RuntimeState.HIGHLIGHT_APPLIED
        self.notes = notes
        return notes

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "sourcePath": self.source_path,
            "mutatesSource": False,
            "overrides": {
                prim: {
                    "prim": item.prim,
                    "color": list(item.color),
                    "intensity": item.intensity,
                    "status": item.status,
                }
                for prim, item in self.overrides.items()
            },
            "notes": list(self.notes),
        }

    @staticmethod
    def _targets_fingerprint(targets: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for item in targets:
            if not isinstance(item, dict):
                continue
            parts.append(
                f"{item.get('prim')}|{item.get('status')}|"
                f"{item.get('intensity')}|{item.get('color')}"
            )
        return ";".join(sorted(parts))
