"""Tests for twinopsctl health."""

from __future__ import annotations

import json
from unittest.mock import patch

from twinops.cli import main


class _Resp:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_health_cli_ok(capsys) -> None:
    payload = {
        "status": "ok",
        "version": "0.3.0",
        "service": "twinops-live",
        "mqtt": {"enabled": False},
    }
    with patch("urllib.request.urlopen", return_value=_Resp(payload)):
        try:
            main(["health", "--base-url", "http://127.0.0.1:8080"])
        except SystemExit as exc:
            assert exc.code == 0
    out = capsys.readouterr().out
    assert "status:  ok" in out
    assert "twinops-live" in out


def test_health_cli_json(capsys) -> None:
    payload = {"status": "ok", "version": "0.3.0"}
    with patch("urllib.request.urlopen", return_value=_Resp(payload)):
        try:
            main(["health", "--json"])
        except SystemExit as exc:
            assert exc.code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_health_cli_unreachable() -> None:
    import urllib.error

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("down"),
    ):
        try:
            main(["health"])
        except SystemExit as exc:
            assert exc.code == 1
