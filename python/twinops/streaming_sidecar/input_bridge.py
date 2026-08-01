"""Browser → Kit input bridge (mouse / keyboard)."""

from __future__ import annotations

import json
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class KitInputBridge:
    """Queue input events; optionally mirror to a JSONL file for Kit extensions."""

    capacity: int = 200
    mirror_path: Path | None = None
    _events: deque[dict[str, Any]] = field(default_factory=deque)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    accepted: int = 0

    def push(self, event: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(event, dict):
            raise ValueError("input event must be an object")
        kind = str(event.get("type") or event.get("kind") or "").strip().lower()
        if kind not in {"mousemove", "mousedown", "mouseup", "keydown", "keyup", "wheel"}:
            raise ValueError(f"unsupported input type: {kind or '(empty)'}")
        item = {
            "type": kind,
            "x": event.get("x"),
            "y": event.get("y"),
            "button": event.get("button"),
            "key": event.get("key"),
            "code": event.get("code"),
            "deltaY": event.get("deltaY"),
            "modifiers": event.get("modifiers") or {},
        }
        with self._lock:
            self._events.append(item)
            while len(self._events) > self.capacity:
                self._events.popleft()
            self.accepted += 1
            if self.mirror_path is not None:
                self.mirror_path.parent.mkdir(parents=True, exist_ok=True)
                with self.mirror_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(item) + "\n")
        return {"ok": True, "accepted": self.accepted, "type": kind}

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._events)
        return items[-max(1, min(limit, self.capacity)) :]

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "accepted": self.accepted,
                "queued": len(self._events),
                "mirrorPath": str(self.mirror_path) if self.mirror_path else None,
            }
