"""In-memory WebRTC signaling for lab Kit streaming demos."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class SignalingSession:
    session_id: str
    offer: dict[str, Any] | None = None
    answer: dict[str, Any] | None = None
    remote_candidates: list[dict[str, Any]] = field(default_factory=list)
    local_candidates: list[dict[str, Any]] = field(default_factory=list)


class WebRTCSignalHub:
    """Tiny signaling hub — browser <-> lab peer (or future Kit sidecar)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SignalingSession] = {}

    def create(self) -> SignalingSession:
        session = SignalingSession(session_id=str(uuid4()))
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> SignalingSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def set_offer(self, session_id: str, offer: dict[str, Any]) -> SignalingSession:
        with self._lock:
            session = self._sessions.setdefault(
                session_id, SignalingSession(session_id=session_id)
            )
            session.offer = offer
            return session

    def set_answer(self, session_id: str, answer: dict[str, Any]) -> SignalingSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.answer = answer
            return session

    def add_candidate(
        self,
        session_id: str,
        candidate: dict[str, Any],
        *,
        local: bool = False,
    ) -> SignalingSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            bucket = session.local_candidates if local else session.remote_candidates
            bucket.append(candidate)
            return session

    def snapshot(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            return {
                "sessionId": session.session_id,
                "offer": session.offer,
                "answer": session.answer,
                "remoteCandidates": list(session.remote_candidates),
                "localCandidates": list(session.local_candidates),
            }


SIGNAL_HUB = WebRTCSignalHub()
