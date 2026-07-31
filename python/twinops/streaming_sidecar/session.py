"""Single-session manager with idle timeout and signaling state."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from twinops.streaming_sidecar.frames import FrameSource, MockFrameSource


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
        }


class StreamingSessionManager:
    """At most one active browser session (reference architecture)."""

    def __init__(
        self,
        *,
        frame_source: FrameSource | None = None,
        idle_timeout_seconds: float = 300.0,
        max_sessions: int = 1,
    ) -> None:
        self.frame_source: FrameSource = frame_source or MockFrameSource()
        self.idle_timeout_seconds = idle_timeout_seconds
        self.max_sessions = max_sessions
        self._lock = threading.RLock()
        self._session: StreamingSession | None = None
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
        self._session.phase = "Deleted"
        self._session = None
        return True

    def set_offer(self, session_id: str, offer: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            session = self._require(session_id)
            session.offer = offer
            session.touch()
            # Lab/sidecar answer contract — real Kit encoder replaces labEcho later.
            answer = {
                "type": "answer",
                "sdp": offer.get("sdp", ""),
                "labEcho": True,
                "provider": "twinops-kit-sidecar",
                "frameSource": self.frame_source.name,
                "note": (
                    "Sidecar accepted offer. Mock/lab path echoes SDP; "
                    "Kit NVENC/App Streaming answer not wired yet."
                ),
            }
            session.answer = answer
            session.phase = "Streaming"
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
        payload = self.frame_source.tick()
        if payload.get("ok"):
            with self._lock:
                if self._session and self._session.session_id == session_id:
                    self._session.frames += 1
                    payload["sessionFrames"] = self._session.frames
        return payload

    def status(self) -> dict[str, Any]:
        with self._lock:
            session = self._session.to_dict() if self._session else None
        return {
            "startedAt": self.started_at,
            "shuttingDown": self.shutting_down,
            "maxSessions": self.max_sessions,
            "idleTimeoutSeconds": self.idle_timeout_seconds,
            "session": session,
            "frameSource": self.frame_source.status(),
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
                    self._session = None
