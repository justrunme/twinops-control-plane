"""Kit App Streaming session descriptors (mock + lab WebRTC)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def webrtc_lab_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    flag = (os.environ.get("TWINOPS_WEBRTC") or "").strip().lower()
    return flag in {"1", "true", "yes", "on", "lab"}


def build_streaming_session(
    *,
    base_url: str = "http://127.0.0.1:8080",
    webrtc: bool | None = None,
) -> dict[str, Any]:
    """Return a Kit streaming session contract.

    - mock: highlight-driven CSS viewport (default)
    - lab-webrtc: browser WebRTC + signaling endpoints (no NVCF/GPU required)
    Real Kit App Streaming later swaps provider/streamUrl to NVIDIA signaling.
    """
    session_id = str(uuid4())
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    base = base_url.rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    enabled = webrtc_lab_enabled(webrtc)
    mode = "lab-webrtc" if enabled else "mock"
    return {
        "apiVersion": "twinops.io/v1alpha1",
        "kind": "KitStreamingSession",
        "metadata": {
            "name": f"{mode}-{session_id[:8]}",
            "createdAt": now,
            "mode": mode,
        },
        "spec": {
            "provider": "twinops-lab-webrtc" if enabled else "twinops-mock",
            "protocol": "twinops.highlight.v1",
            "sceneUrl": f"{base}/api/scene",
            "eventsUrl": f"{ws_base}/ws/events",
            "streamUrl": f"{base}/api/streaming/webrtc" if enabled else None,
            "webrtc": {
                "enabled": enabled,
                "signalingUrl": f"{base}/api/streaming/webrtc/signal" if enabled else None,
                "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}] if enabled else [],
                "notes": (
                    "Lab WebRTC: browser MediaStream from scene canvas + REST signaling. "
                    "Replace provider with Kit App Streaming for GPU frames."
                    if enabled
                    else "Placeholder until TWINOPS_WEBRTC=1 / --webrtc"
                ),
            },
        },
        "status": {
            "phase": "WebRTCLabReady" if enabled else "MockReady",
            "message": (
                "Lab WebRTC signaling ready — browser attaches scene MediaStream"
                if enabled
                else "GPU stream not provisioned — use highlight contract + mock viewport"
            ),
            "sessionId": session_id,
        },
    }


def mock_streaming_session(*, base_url: str = "http://127.0.0.1:8080") -> dict[str, Any]:
    """Backward-compatible alias (mock mode)."""
    return build_streaming_session(base_url=base_url, webrtc=False)
