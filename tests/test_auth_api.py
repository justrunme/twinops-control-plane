"""Tests for optional live API token auth."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from twinops.api.app import create_app

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def test_api_token_gates_control_plane(tmp_path: Path) -> None:
    app = create_app(
        example_dir=EXAMPLE,
        work_dir=tmp_path / "live",
        interval_seconds=60,
        autostart=False,
        api_token="secret-demo",
    )
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/ready").status_code == 200
        denied = client.get("/api/twin")
        assert denied.status_code == 401
        ok = client.get("/api/twin", headers={"Authorization": "Bearer secret-demo"})
        assert ok.status_code == 200
        stream = client.get(
            "/api/streaming/session",
            headers={"X-TwinOps-Token": "secret-demo"},
        )
        assert stream.status_code == 200
        body = stream.json()
        assert body["kind"] == "KitStreamingSession"
        assert body["metadata"]["mode"] == "mock"
