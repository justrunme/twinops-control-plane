"""Host NVENC ingest bridge via ffmpeg → MPEG-TS for aiortc MediaPlayer.

This proves GPU encode on the host. aiortc still re-encodes for WebRTC RTP
after MediaPlayer decodes the MPEG-TS stream.

Kit-file mode watches the drop directory and restarts ffmpeg when a newer
JPEG/PNG appears so frames after session start are picked up.
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
    watch_interval: float = 0.5
    _proc: subprocess.Popen[str] | None = None
    _port: int | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stop: threading.Event = field(default_factory=threading.Event)
    _watcher: threading.Thread | None = None
    _source_path: str | None = None
    _source_mtime: float | None = None
    started_at: float | None = None
    last_error: str | None = None
    restarts: int = 0

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
            self._stop.clear()
            port = self._port or _free_udp_port()
            self._port = port
            self._start_unlocked(port)
            self.started_at = time.time()
        if self.frame_dir is not None:
            self._watcher = threading.Thread(
                target=self._watch_loop, name="twinops-nvenc-watch", daemon=True
            )
            self._watcher.start()
        return f"udp://127.0.0.1:{self._port}"

    def stop(self) -> None:
        self._stop.set()
        if self._watcher and self._watcher.is_alive():
            self._watcher.join(timeout=2)
        self._watcher = None
        with self._lock:
            self._stop_proc_unlocked()
            self._port = None

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "url": self.url,
            "fps": self.fps,
            "frameDir": str(self.frame_dir) if self.frame_dir else None,
            "sourcePath": self._source_path,
            "gpuIndex": self.gpu_index,
            "ingestCodec": "h264_nvenc",
            "role": "ingest-bridge",
            "note": "ffmpeg NVENC → MPEG-TS; WebRTC RTP still encoded by aiortc",
            "lastError": self.last_error,
            "startedAt": self.started_at,
            "restarts": self.restarts,
        }

    def _watch_loop(self) -> None:
        while not self._stop.wait(self.watch_interval):
            latest = self._latest_still()
            if latest is None:
                continue
            mtime = latest.stat().st_mtime
            with self._lock:
                if self._source_path == str(latest) and self._source_mtime == mtime:
                    continue
                if self._port is None:
                    continue
                logger.info("kit frame changed (%s) — restarting NVENC ffmpeg", latest)
                self._stop_proc_unlocked()
                try:
                    self._start_unlocked(self._port)
                    self.restarts += 1
                except RuntimeError as exc:
                    logger.warning("NVENC restart failed: %s", exc)

    def _start_unlocked(self, port: int) -> None:
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
        self.last_error = None
        time.sleep(0.35)
        if self._proc.poll() is not None:
            err = ""
            if self._proc.stderr is not None:
                err = self._proc.stderr.read() or ""
            self.last_error = err.strip() or f"ffmpeg exited {self._proc.returncode}"
            self._proc = None
            raise RuntimeError(f"ffmpeg NVENC failed: {self.last_error}")

    def _stop_proc_unlocked(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def _latest_still(self) -> Path | None:
        if self.frame_dir is None:
            return None
        self.frame_dir.mkdir(parents=True, exist_ok=True)
        stills = sorted(
            [
                *self.frame_dir.glob("*.jpg"),
                *self.frame_dir.glob("*.jpeg"),
                *self.frame_dir.glob("*.png"),
            ],
            key=lambda path: path.stat().st_mtime,
        )
        return stills[-1] if stills else None

    def _build_command(self, port: int) -> list[str]:
        latest = self._latest_still()
        if latest is not None:
            self._source_path = str(latest)
            self._source_mtime = latest.stat().st_mtime
            inputs = [
                "-loop",
                "1",
                "-framerate",
                str(self.fps),
                "-i",
                str(latest),
            ]
        else:
            self._source_path = f"lavfi:testsrc@{self.width}x{self.height}"
            self._source_mtime = None
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
