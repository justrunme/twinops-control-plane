"""Tests for lab WebRTC session + signaling."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from twinops.api.app import create_app

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def test_webrtc_lab_session_and_signal(tmp_path: Path) -> None:
    app = create_app(
        example_dir=EXAMPLE,
        work_dir=tmp_path / "live",
        interval_seconds=60,
        autostart=False,
        webrtc=True,
    )
    with TestClient(app) as client:
        session = client.get("/api/streaming/session").json()
        assert session["metadata"]["mode"] == "lab-webrtc"
        assert session["spec"]["webrtc"]["enabled"] is True
        created = client.post(
            "/api/streaming/webrtc/signal", json={"action": "create"}
        ).json()
        assert created["ok"] is True
        sid = created["sessionId"]
        offered = client.post(
            "/api/streaming/webrtc/signal",
            json={
                "action": "offer",
                "sessionId": sid,
                "sdp": {"type": "offer", "sdp": "v=0"},
            },
        ).json()
        assert offered["ok"] is True
        assert offered["answer"]["labEcho"] is True
