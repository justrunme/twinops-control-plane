"""Single-session Kit streaming sidecar."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient
from twinops.api.app import create_app
from twinops.api.streaming import build_streaming_session
from twinops.streaming_sidecar.app import create_sidecar_app
from twinops.streaming_sidecar.config import SidecarConfig
from twinops.streaming_sidecar.session import StreamingSessionManager

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def test_session_create_delete_and_single_limit() -> None:
    mgr = StreamingSessionManager(idle_timeout_seconds=60)
    mgr.start()
    try:
        first = mgr.create(client_id="browser-a")
        assert first.phase == "Ready"
        try:
            mgr.create(client_id="browser-b")
            raise AssertionError("expected single-session limit")
        except RuntimeError as exc:
            assert "single-session" in str(exc)
        assert mgr.delete(first.session_id) is True
        second = mgr.create(client_id="browser-c")
        assert second.session_id != first.session_id
    finally:
        mgr.stop()


def test_offer_frame_and_idle_timeout() -> None:
    mgr = StreamingSessionManager(idle_timeout_seconds=0.2)
    mgr.start()
    try:
        session = mgr.create()
        answer = mgr.set_offer(session.session_id, {"type": "offer", "sdp": "v=0"})
        assert answer["labEcho"] is True
        assert answer["provider"] == "twinops-kit-sidecar"
        frame = mgr.tick_frames(session.session_id)
        assert frame["ok"] is True
        # Force idle reap
        session.last_seen -= 10
        import time

        time.sleep(1.2)
        assert mgr.active() is None
    finally:
        mgr.stop()


def test_sidecar_http_api() -> None:
    app = create_sidecar_app(
        SidecarConfig(host="127.0.0.1", port=8091, idle_timeout_seconds=120)
    )
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/ready").json()["status"] == "ready"
        created = client.post("/v1/sessions", json={"clientId": "ci"}).json()
        assert created["ok"] is True
        sid = created["session"]["sessionId"]
        conflict = client.post("/v1/sessions", json={})
        assert conflict.status_code == 409
        signaled = client.post(
            f"/v1/sessions/{sid}/signal",
            json={"action": "offer", "sdp": {"type": "offer", "sdp": "v=0"}},
        ).json()
        assert signaled["answer"]["labEcho"] is True
        frame = client.post(f"/v1/sessions/{sid}/frame").json()
        assert frame["ok"] is True
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "twinops_sidecar_sessions" in metrics.text
        assert client.delete(f"/v1/sessions/{sid}").json()["ok"] is True


def test_live_api_points_at_sidecar(tmp_path: Path) -> None:
    os.environ["TWINOPS_STREAMING_SIDECAR_URL"] = "http://127.0.0.1:8091"
    try:
        session = build_streaming_session(
            base_url="http://127.0.0.1:8080",
            sidecar="http://127.0.0.1:8091",
        )
        assert session["metadata"]["mode"] == "kit-sidecar"
        assert session["spec"]["sidecarUrl"] == "http://127.0.0.1:8091"
        app = create_app(
            example_dir=EXAMPLE,
            work_dir=tmp_path / "live",
            interval_seconds=60,
            autostart=False,
            streaming_sidecar_url="http://127.0.0.1:8091",
        )
        with TestClient(app) as client:
            payload = client.get("/api/streaming/session").json()
            assert payload["metadata"]["mode"] == "kit-sidecar"
    finally:
        os.environ.pop("TWINOPS_STREAMING_SIDECAR_URL", None)
