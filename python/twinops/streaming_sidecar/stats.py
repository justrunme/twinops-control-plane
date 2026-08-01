"""Streaming session quality stats (startup, FPS, bitrate, disconnects)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamStats:
    session_created_at: float = field(default_factory=time.time)
    media_ready_at: float | None = None
    frames: int = 0
    bytes_estimate: int = 0
    disconnects: int = 0
    last_frame_at: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def mark_media_ready(self) -> None:
        with self._lock:
            if self.media_ready_at is None:
                self.media_ready_at = time.time()

    def record_frame(self, *, bytes_estimate: int = 0) -> None:
        with self._lock:
            self.frames += 1
            self.bytes_estimate += max(0, bytes_estimate)
            self.last_frame_at = time.time()

    def record_disconnect(self) -> None:
        with self._lock:
            self.disconnects += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            created = self.session_created_at
            ready = self.media_ready_at
            frames = self.frames
            nbytes = self.bytes_estimate
            disconnects = self.disconnects
            last = self.last_frame_at
        now = time.time()
        startup_ms = None if ready is None else int((ready - created) * 1000)
        elapsed = max(0.001, (last or now) - created)
        fps = frames / elapsed if frames else 0.0
        bitrate_kbps = (nbytes * 8 / elapsed) / 1000.0 if nbytes else 0.0
        return {
            "startupTimeMs": startup_ms,
            "frames": frames,
            "fps": round(fps, 2),
            "bitrateKbps": round(bitrate_kbps, 2),
            "disconnects": disconnects,
            "bytesEstimate": nbytes,
        }
