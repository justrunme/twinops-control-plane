"""Kit App Streaming session descriptors (mock / lab WebRTC / kit sidecar)."""

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


def sidecar_url(explicit: str | None = None) -> str | None:
    if explicit is not None:
        value = explicit.strip()
        return value or None
    env = (os.environ.get("TWINOPS_STREAMING_SIDECAR_URL") or "").strip()
    return env or None


def build_streaming_session(
    *,
    base_url: str = "http://127.0.0.1:8080",
    webrtc: bool | None = None,
    sidecar: str | None = None,
) -> dict[str, Any]:
    """Return a Kit streaming session contract.

    Modes:
    - mock: highlight-driven CSS viewport (default)
    - lab-webrtc: browser WebRTC + TwinOps signaling (no GPU)
    - kit-sidecar: single-session streaming sidecar (mock or Kit process)
    """
    session_id = str(uuid4())
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    base = base_url.rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    side = sidecar_url(sidecar)
    enabled = webrtc_lab_enabled(webrtc) or bool(side)

    if side:
        mode = "kit-sidecar"
        provider = "twinops-kit-sidecar"
        stream_url = f"{side.rstrip('/')}/v1/status"
        signaling = f"{side.rstrip('/')}/v1/sessions"
        phase = "SidecarReady"
        message = (
            "Kit streaming sidecar ready — create a single session at /v1/sessions"
        )
        notes = (
            "Single-session sidecar (mock frames or Kit supervisor). "
            "Not multi-tenant NVCF; WebRTC answer remains lab-echo until encoder lands."
        )
    elif enabled:
        mode = "lab-webrtc"
        provider = "twinops-lab-webrtc"
        stream_url = f"{base}/api/streaming/webrtc"
        signaling = f"{base}/api/streaming/webrtc/signal"
        phase = "WebRTCLabReady"
        message = "Lab WebRTC signaling ready — browser attaches scene MediaStream"
        notes = (
            "Lab WebRTC: browser MediaStream from scene canvas + REST signaling. "
            "Point TWINOPS_STREAMING_SIDECAR_URL at the sidecar for kit-sidecar mode."
        )
    else:
        mode = "mock"
        provider = "twinops-mock"
        stream_url = None
        signaling = None
        phase = "MockReady"
        message = "GPU stream not provisioned — use highlight contract + mock viewport"
        notes = "Placeholder until TWINOPS_WEBRTC=1 / --webrtc or streaming sidecar URL"

    return {
        "apiVersion": "twinops.io/v1alpha1",
        "kind": "KitStreamingSession",
        "metadata": {
            "name": f"{mode}-{session_id[:8]}",
            "createdAt": now,
            "mode": mode,
        },
        "spec": {
            "provider": provider,
            "protocol": "twinops.highlight.v1",
            "sceneUrl": f"{base}/api/scene",
            "eventsUrl": f"{ws_base}/ws/events",
            "streamUrl": stream_url,
            "sidecarUrl": side,
            "webrtc": {
                "enabled": enabled,
                "signalingUrl": signaling,
                "iceServers": (
                    [{"urls": ["stun:stun.l.google.com:19302"]}] if enabled else []
                ),
                "notes": notes,
            },
        },
        "status": {
            "phase": phase,
            "message": message,
            "sessionId": session_id,
        },
    }


def mock_streaming_session(*, base_url: str = "http://127.0.0.1:8080") -> dict[str, Any]:
    """Backward-compatible alias (mock mode)."""
    return build_streaming_session(base_url=base_url, webrtc=False, sidecar=None)
