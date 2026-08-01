"""Single-session Kit streaming sidecar (v1.1 encoder path)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi.testclient import TestClient
from twinops.api.app import create_app
from twinops.api.streaming import build_streaming_session
from twinops.streaming_sidecar.app import create_sidecar_app
from twinops.streaming_sidecar.config import SidecarConfig
from twinops.streaming_sidecar.encoder import probe_encoder
from twinops.streaming_sidecar.frames import KitFileFrameSource, select_frame_source
from twinops.streaming_sidecar.input_bridge import KitInputBridge
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
    mgr = StreamingSessionManager(idle_timeout_seconds=0.2, encoder="mock")
    mgr.start()
    try:
        session = mgr.create()
        answer = asyncio.run(
            mgr.answer_offer(session.session_id, {"type": "offer", "sdp": "v=0"})
        )
        assert answer["labEcho"] is True
        assert answer["provider"] == "twinops-kit-sidecar"
        assert answer["encoder"] == "mock"
        frame = mgr.tick_frames(session.session_id)
        assert frame["ok"] is True
        assert "stats" in frame
        session.last_seen -= 10
        import time

        time.sleep(1.2)
        assert mgr.active() is None
    finally:
        mgr.stop()


def test_encoder_probe_mock_and_auto() -> None:
    forced = probe_encoder("mock")
    assert forced.backend == "mock"
    auto = probe_encoder("auto")
    assert auto.backend in {"mock", "software", "nvenc"}
    assert "realWebRtcMedia" in auto.to_dict()


def test_input_bridge_and_mirror(tmp_path: Path) -> None:
    mirror = tmp_path / "input.jsonl"
    bridge = KitInputBridge(mirror_path=mirror)
    out = bridge.push({"type": "mousemove", "x": 10, "y": 20})
    assert out["ok"] is True
    assert bridge.accepted == 1
    assert mirror.read_text(encoding="utf-8").strip()
    try:
        bridge.push({"type": "explode"})
        raise AssertionError("expected unsupported type")
    except ValueError:
        pass


def test_kit_file_frame_source(tmp_path: Path) -> None:
    source = KitFileFrameSource(directory=tmp_path / "frames")
    source.start()
    try:
        waiting = source.tick()
        assert waiting["ok"] is True
        assert waiting.get("waitingForKitFrame") is True
        drop = tmp_path / "frames" / "frame-001.ppm"
        # Minimal P6 PPM 2x2
        drop.write_bytes(b"P6\n2 2\n255\n" + bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 1, 1, 1]))
        got = source.tick()
        assert got["ok"] is True
        assert got.get("path") == str(drop)
    finally:
        source.stop()


def test_select_frame_source_kit_file(tmp_path: Path) -> None:
    src = select_frame_source("kit-file", kit_frame_dir=tmp_path)
    assert src.name == "kit-file"


def test_sidecar_http_api(tmp_path: Path) -> None:
    app = create_sidecar_app(
        SidecarConfig(
            host="127.0.0.1",
            port=8091,
            idle_timeout_seconds=120,
            encoder="mock",
            input_mirror=str(tmp_path / "mirror.jsonl"),
        )
    )
    with TestClient(app) as client:
        health = client.get("/health").json()
        assert health["status"] == "ok"
        assert health["encoder"] == "mock"
        ready = client.get("/ready").json()
        assert ready["status"] == "ready"
        assert ready["encoder"]["backend"] == "mock"
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
        assert "stats" in frame
        inp = client.post(
            f"/v1/sessions/{sid}/input",
            json={"type": "keydown", "key": "a", "code": "KeyA"},
        ).json()
        assert inp["ok"] is True
        status = client.get("/v1/status").json()
        assert status["encoder"]["backend"] == "mock"
        assert status["input"]["accepted"] >= 1
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "twinops_sidecar_sessions" in metrics.text
        assert "twinops_sidecar_stream_fps" in metrics.text
        assert 'twinops_sidecar_encoder{backend="mock"}' in metrics.text
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
