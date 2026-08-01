"""Single-session manager with idle timeout, media, and input bridge."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from twinops.streaming_sidecar.encoder import EncoderCapability, probe_encoder
from twinops.streaming_sidecar.frames import FrameSource, MockFrameSource
from twinops.streaming_sidecar.input_bridge import KitInputBridge
from twinops.streaming_sidecar.stats import StreamStats
from twinops.streaming_sidecar.webrtc_media import WebRTCMediaSession


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class StreamingSession:
    session_id: str
    created_at: str
    client_id: str = ""
    phase: str = "Created"
    offer: dict[str, Any] | None = None
    answer: dict[str, Any] | None = None
    remote_candidates: list[dict[str, Any]] = field(default_factory=list)
    local_candidates: list[dict[str, Any]] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)
    frames: int = 0
    stats: StreamStats = field(default_factory=StreamStats)

    def touch(self) -> None:
        self.last_seen = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "createdAt": self.created_at,
            "clientId": self.client_id,
            "phase": self.phase,
            "offer": self.offer,
            "answer": self.answer,
            "remoteCandidates": list(self.remote_candidates),
            "localCandidates": list(self.local_candidates),
            "frames": self.frames,
            "idleSeconds": max(0.0, time.time() - self.last_seen),
            "stats": self.stats.snapshot(),
        }


class StreamingSessionManager:
    """At most one active browser session (reference architecture)."""

    def __init__(
        self,
        *,
        frame_source: FrameSource | None = None,
        idle_timeout_seconds: float = 300.0,
        max_sessions: int = 1,
        encoder: str = "auto",
        input_mirror: str | Path | None = None,
        kit_frame_dir: str | Path | None = None,
        gpu_index: int = 0,
    ) -> None:
        self.frame_source: FrameSource = frame_source or MockFrameSource()
        self.idle_timeout_seconds = idle_timeout_seconds
        self.max_sessions = max_sessions
        self.capability: EncoderCapability = probe_encoder(encoder)
        self.kit_frame_dir = Path(kit_frame_dir) if kit_frame_dir else None
        self.gpu_index = gpu_index
        mirror = Path(input_mirror) if input_mirror else None
        self.input_bridge = KitInputBridge(mirror_path=mirror)
        self._lock = threading.RLock()
        self._session: StreamingSession | None = None
        self._media: WebRTCMediaSession | None = None
        self._stop = threading.Event()
        self._reaper: threading.Thread | None = None
        self.started_at = _utcnow()
        self.shutting_down = False

    def start(self) -> None:
        self.frame_source.start()
        self._stop.clear()
        if self._reaper and self._reaper.is_alive():
            return
        self._reaper = threading.Thread(
            target=self._reap_loop, name="twinops-sidecar-reaper", daemon=True
        )
        self._reaper.start()

    def stop(self) -> None:
        self.shutting_down = True
        self._stop.set()
        with self._lock:
            if self._session is not None:
                self._delete_unlocked(self._session.session_id)
        self.frame_source.stop()
        if self._reaper and self._reaper.is_alive():
            self._reaper.join(timeout=2)
        self._reaper = None

    def create(self, *, client_id: str = "") -> StreamingSession:
        with self._lock:
            if self.shutting_down:
                raise RuntimeError("sidecar is shutting down")
            if self._session is not None:
                raise RuntimeError(
                    "single-session limit: delete the active session first "
                    f"({self._session.session_id})"
                )
            session = StreamingSession(
                session_id=str(uuid4()),
                created_at=_utcnow(),
                client_id=client_id,
                phase="Ready",
            )
            self._session = session
            self._media = WebRTCMediaSession(
                frame_source=self.frame_source,
                capability=self.capability,
                input_bridge=self.input_bridge,
                stats=session.stats,
                kit_frame_dir=self.kit_frame_dir,
                gpu_index=self.gpu_index,
            )
            return session

    def get(self, session_id: str) -> StreamingSession | None:
        with self._lock:
            if self._session and self._session.session_id == session_id:
                return self._session
            return None

    def active(self) -> StreamingSession | None:
        with self._lock:
            return self._session

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._delete_unlocked(session_id)

    def _delete_unlocked(self, session_id: str) -> bool:
        if self._session is None or self._session.session_id != session_id:
            return False
        media = self._media
        self._media = None
        self._session.phase = "Deleted"
        self._session = None
        if media is not None:
            # Best-effort sync close from worker thread / sync callers.
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(media.close())
            else:
                loop.create_task(media.close())
        return True

    async def answer_offer(
        self, session_id: str, offer: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            session = self._require(session_id)
            session.offer = offer
            session.touch()
            media = self._media
        if media is None:
            raise RuntimeError("media session missing")
        answer = await media.answer_offer(offer)
        with self._lock:
            if self._session and self._session.session_id == session_id:
                self._session.answer = answer
                self._session.phase = "Streaming"
                self._session.touch()
        return answer

    def add_candidate(
        self,
        session_id: str,
        candidate: dict[str, Any],
        *,
        local: bool = False,
    ) -> None:
        with self._lock:
            session = self._require(session_id)
            bucket = session.local_candidates if local else session.remote_candidates
            bucket.append(candidate)
            session.touch()

    def tick_frames(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._require(session_id)
            session.touch()
            stats = session.stats
        payload = self.frame_source.tick()
        if payload.get("ok"):
            width = int(payload.get("width") or 0)
            height = int(payload.get("height") or 0)
            stats.record_frame(bytes_estimate=max(0, width * height * 3))
            with self._lock:
                if self._session and self._session.session_id == session_id:
                    self._session.frames += 1
                    payload["sessionFrames"] = self._session.frames
                    payload["stats"] = stats.snapshot()
        return payload

    def push_input(self, session_id: str, event: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            session = self._require(session_id)
            session.touch()
        return self.input_bridge.push(event)

    def status(self) -> dict[str, Any]:
        with self._lock:
            session = self._session.to_dict() if self._session else None
        media = self._media
        return {
            "startedAt": self.started_at,
            "shuttingDown": self.shutting_down,
            "maxSessions": self.max_sessions,
            "idleTimeoutSeconds": self.idle_timeout_seconds,
            "session": session,
            "frameSource": self.frame_source.status(),
            "encoder": self.capability.to_dict(),
            "ingestEncoder": media.ingest_encoder if media else "none",
            "webrtcEncoder": media.webrtc_encoder if media else "none",
            "encoderInUse": media.encoder_in_use if media else "none",
            "mediaPath": media.media_path if media else "idle",
            "input": self.input_bridge.status(),
        }

    def _require(self, session_id: str) -> StreamingSession:
        if self._session is None or self._session.session_id != session_id:
            raise KeyError(f"unknown session: {session_id}")
        return self._session

    def _reap_loop(self) -> None:
        while not self._stop.wait(1.0):
            with self._lock:
                session = self._session
                if session is None:
                    continue
                idle = time.time() - session.last_seen
                if idle >= self.idle_timeout_seconds:
                    session.phase = "IdleTimeout"
                    self._delete_unlocked(session.session_id)
