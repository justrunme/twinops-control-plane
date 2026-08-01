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
                    "Pair with frame_source=kit-file for RGBA/JPEG drop directory",
                    "Single GPU / single session assumed",
                ],
            }


@dataclass
class KitFileFrameSource:
    """Read latest frame dropped by Kit (JPEG/PNG/PPM) from a directory."""

    directory: Path
    width: int = 1280
    height: int = 720
    fps: float = 30.0
    name: str = "kit-file"
    frames_emitted: int = 0
    _running: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_path: str | None = None

    def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._running = True

    def stop(self) -> None:
        with self._lock:
            self._running = False

    def tick(self) -> dict[str, Any]:
        with self._lock:
            if not self._running:
                return {"ok": False, "error": "not running"}
            candidates = sorted(
                [
                    *self.directory.glob("*.jpg"),
                    *self.directory.glob("*.jpeg"),
                    *self.directory.glob("*.png"),
                    *self.directory.glob("*.ppm"),
                ],
                key=lambda path: path.stat().st_mtime,
            )
            if not candidates:
                # Keep WebRTC alive with a deterministic placeholder until Kit drops frames.
                self.frames_emitted += 1
                n = self.frames_emitted
                return {
                    "ok": True,
                    "frame": n,
                    "width": self.width,
                    "height": self.height,
                    "fps": self.fps,
                    "pixel": [(n * 11) % 256, 32, 64],
                    "source": self.name,
                    "waitingForKitFrame": True,
                    "ts": time.time(),
                }
            latest = candidates[-1]
            self._last_path = str(latest)
            self.frames_emitted += 1
            # Pixel hint from file size — decoder fills the WebRTC track separately.
            size = latest.stat().st_size
            return {
                "ok": True,
                "frame": self.frames_emitted,
                "width": self.width,
                "height": self.height,
                "fps": self.fps,
                "pixel": [size % 256, (size // 3) % 256, (size // 7) % 256],
                "path": self._last_path,
                "bytes": size,
                "source": self.name,
                "ts": time.time(),
            }

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "running": self._running,
            "directory": str(self.directory),
            "framesEmitted": self.frames_emitted,
            "lastPath": self._last_path,
            "limitations": [
                "Kit (or a helper) must write JPEG/PNG/PPM into the directory",
                "WebRTC track samples color/metadata; full texture decode is best-effort",
            ],
        }


def select_frame_source(
    kind: str,
    *,
    kit_command: str | None = None,
    kit_frame_dir: str | Path | None = None,
) -> FrameSource:
    kind = (kind or "mock").strip().lower()
    if kind == "kit":
        if not kit_command:
            raise ValueError("frame_source=kit requires TWINOPS_KIT_COMMAND")
        return KitFrameSource(command=kit_command)
    if kind in {"kit-file", "file"}:
        path = Path(kit_frame_dir or "/tmp/twinops-kit-frames")
        return KitFileFrameSource(directory=path)
    return MockFrameSource()
