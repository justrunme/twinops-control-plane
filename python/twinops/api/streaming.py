"""Mock Kit App Streaming session descriptors (GPU-free demos)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def mock_streaming_session(*, base_url: str = "http://127.0.0.1:8080") -> dict[str, Any]:
    """Return a placeholder Kit streaming session contract.

    Real NVCF / Kit App Streaming integration replaces `streamUrl` with an
    authenticated WebRTC/WebSocket endpoint. Until then the web UI keeps using
    the mock viewport driven by `twinops.highlight.v1`.
    """
    session_id = str(uuid4())
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "apiVersion": "twinops.io/v1alpha1",
        "kind": "KitStreamingSession",
        "metadata": {
            "name": f"mock-{session_id[:8]}",
            "createdAt": now,
            "mode": "mock",
        },
        "spec": {
            "provider": "twinops-mock",
            "protocol": "twinops.highlight.v1",
            "sceneUrl": f"{base_url.rstrip('/')}/api/scene",
            "eventsUrl": f"{base_url.rstrip('/').replace('http', 'ws', 1)}/ws/events",
            "streamUrl": None,
        },
        "status": {
            "phase": "MockReady",
            "message": "GPU stream not provisioned — use highlight contract + mock viewport",
            "sessionId": session_id,
        },
    }
