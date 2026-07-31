"""Tests for demo SSO JWT helpers and auth acceptance."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from twinops.api.app import create_app
from twinops.api.sso import issue_demo_jwt, validate_hs256_jwt

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def test_issue_and_validate_jwt() -> None:
    token = issue_demo_jwt(secret="s3cret", subject="alice", audience="twinops-live")
    claims = validate_hs256_jwt(token, secret="s3cret", audience="twinops-live")
    assert claims is not None
    assert claims["sub"] == "alice"


def test_sso_jwt_gates_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TWINOPS_SSO_AUDIENCE", "twinops-live")
    app = create_app(
        example_dir=EXAMPLE,
        work_dir=tmp_path / "live",
        interval_seconds=60,
        autostart=False,
        sso_secret="s3cret",
    )
    token = issue_demo_jwt(secret="s3cret", subject="bob")
    with TestClient(app) as client:
        assert client.get("/api/twin").status_code == 401
        ok = client.get("/api/twin", headers={"Authorization": f"Bearer {token}"})
        assert ok.status_code == 200
