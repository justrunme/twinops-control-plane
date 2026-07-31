"""Frame sources for the streaming sidecar.

``MockFrameSource`` generates deterministic synthetic frames for CI/demo hosts
without Omniverse. ``KitFrameSource`` is a process supervisor stub that launches
a Kit command when configured — real RTX frame capture plugs in later.
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FrameSource(Protocol):
    name: str

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def tick(self) -> dict[str, Any]: ...

    def status(self) -> dict[str, Any]: ...


@dataclass
class MockFrameSource:
    """Synthetic frame generator — no GPU / WebRTC stack required."""

    width: int = 1280
    height: int = 720
    fps: float = 15.0
    name: str = "mock"
    frames_emitted: int = 0
    _running: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        with self._lock:
            self._running = True

    def stop(self) -> None:
        with self._lock:
            self._running = False

    def tick(self) -> dict[str, Any]:
        with self._lock:
            if not self._running:
                return {"ok": False, "error": "not running"}
            self.frames_emitted += 1
            n = self.frames_emitted
        # Deterministic RGB pulse (documented as placeholder for RTX frames).
        r = (n * 17) % 256
        g = (n * 29) % 256
        b = (n * 43) % 256
        return {
            "ok": True,
            "frame": n,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "pixel": [r, g, b],
            "ts": time.time(),
            "source": self.name,
        }

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "running": self._running,
            "framesEmitted": self.frames_emitted,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "limitations": [
                "Synthetic frames only — not Omniverse RTX pixels",
                "WebRTC MediaStream attach is browser/lab path until Kit encoder wires in",
            ],
        }


@dataclass
class KitFrameSource:
    """Optional Kit process supervisor — does not capture RTX frames yet."""

    command: str
    name: str = "kit"
    frames_emitted: int = 0
    _proc: subprocess.Popen[str] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    log_path: Path | None = None

    def start(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return
            log = self.log_path or Path("/tmp/twinops-kit-sidecar.log")
            log.parent.mkdir(parents=True, exist_ok=True)
            handle = log.open("a", encoding="utf-8")
            self._proc = subprocess.Popen(
                self.command,
                shell=True,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )

    def stop(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None

    def tick(self) -> dict[str, Any]:
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            if running:
                self.frames_emitted += 1
            return {
                "ok": running,
                "frame": self.frames_emitted,
                "source": self.name,
                "pid": self._proc.pid if self._proc else None,
                "note": (
                    "Kit process supervised; RTX frame grab not wired — "
                    "use mock source for CI MediaStream demos"
                ),
                "ts": time.time(),
            }

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            return {
                "name": self.name,
                "running": running,
                "pid": self._proc.pid if self._proc else None,
                "command": self.command,
                "framesEmitted": self.frames_emitted,
                "limitations": [
                    "Starts Kit via TWINOPS_KIT_COMMAND only",
                    "No NVENC/App Streaming encoder in this release",
                    "Single GPU / single session assumed",
                ],
            }


def select_frame_source(
    kind: str,
    *,
    kit_command: str | None = None,
) -> FrameSource:
    kind = (kind or "mock").strip().lower()
    if kind == "kit":
        if not kit_command:
            raise ValueError("frame_source=kit requires TWINOPS_KIT_COMMAND")
        return KitFrameSource(command=kit_command)
    return MockFrameSource()
