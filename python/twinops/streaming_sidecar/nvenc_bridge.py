"""Host NVENC bridge via ffmpeg → MPEG-TS for aiortc MediaPlayer.

When ``h264_nvenc`` is available, frames from a kit-file directory (or a
synthetic lavfi pattern) are encoded on the GPU and exposed as a local MPEG-TS
UDP stream that aiortc can ingest. This is the single-session / single-GPU path
— not NVCF.
"""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class NVENCBridge:
    """Owns one ffmpeg NVENC process feeding a local MPEG-TS UDP endpoint."""

    frame_dir: Path | None = None
    fps: int = 30
    width: int = 1280
    height: int = 720
    gpu_index: int = 0
    _proc: subprocess.Popen[str] | None = None
    _port: int | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    started_at: float | None = None
    last_error: str | None = None

    @property
    def url(self) -> str | None:
        if self._port is None:
            return None
        return f"udp://127.0.0.1:{self._port}"

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(self) -> str:
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg not found — required for NVENC bridge")
        with self._lock:
            if self._proc and self._proc.poll() is None and self._port:
                return f"udp://127.0.0.1:{self._port}"
            self.stop_unlocked()
            port = _free_udp_port()
            cmd = self._build_command(port)
            logger.info("starting NVENC ffmpeg bridge: %s", " ".join(cmd))
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except OSError as exc:
                self.last_error = str(exc)
                raise RuntimeError(f"failed to start ffmpeg NVENC: {exc}") from exc
            self._port = port
            self.started_at = time.time()
            self.last_error = None
            # Brief settle so MediaPlayer can attach.
            time.sleep(0.35)
            if self._proc.poll() is not None:
                err = ""
                if self._proc.stderr is not None:
                    err = self._proc.stderr.read() or ""
                self.last_error = err.strip() or f"ffmpeg exited {self._proc.returncode}"
                self._proc = None
                self._port = None
                raise RuntimeError(f"ffmpeg NVENC failed: {self.last_error}")
            return f"udp://127.0.0.1:{port}"

    def stop(self) -> None:
        with self._lock:
            self.stop_unlocked()

    def stop_unlocked(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self._port = None

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "url": self.url,
            "fps": self.fps,
            "frameDir": str(self.frame_dir) if self.frame_dir else None,
            "gpuIndex": self.gpu_index,
            "codec": "h264_nvenc",
            "lastError": self.last_error,
            "startedAt": self.started_at,
        }

    def _build_command(self, port: int) -> list[str]:
        # Prefer kit-file stills when present; otherwise synthetic pattern proves NVENC.
        inputs: list[str]
        if self.frame_dir is not None:
            self.frame_dir.mkdir(parents=True, exist_ok=True)
            stills = sorted(
                [
                    *self.frame_dir.glob("*.jpg"),
                    *self.frame_dir.glob("*.jpeg"),
                    *self.frame_dir.glob("*.png"),
                ]
            )
            if stills:
                # Concat demuxer over a temporary list would be ideal; image2 with
                # the newest still looped is enough for single-session demos.
                latest = stills[-1]
                inputs = [
                    "-loop",
                    "1",
                    "-framerate",
                    str(self.fps),
                    "-i",
                    str(latest),
                ]
            else:
                inputs = [
                    "-f",
                    "lavfi",
                    "-i",
                    f"testsrc=size={self.width}x{self.height}:rate={self.fps}",
                ]
        else:
            inputs = [
                "-f",
                "lavfi",
                "-i",
                f"testsrc=size={self.width}x{self.height}:rate={self.fps}",
            ]
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-re",
            *inputs,
            "-an",
            "-c:v",
            "h264_nvenc",
            "-gpu",
            str(self.gpu_index),
            "-preset",
            "p4",
            "-tune",
            "ll",
            "-bf",
            "0",
            "-g",
            str(self.fps),
            "-f",
            "mpegts",
            f"udp://127.0.0.1:{port}?pkt_size=1316",
        ]
