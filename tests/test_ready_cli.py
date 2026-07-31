"""Tests for twinopsctl ready."""

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


def test_ready_cli_ok(capsys) -> None:
    payload = {
        "status": "ready",
        "version": "0.3.3",
        "twin": "assembly-line-a",
        "hasDriftReport": True,
    }
    with patch("urllib.request.urlopen", return_value=_Resp(payload)):
        try:
            main(["ready"])
        except SystemExit as exc:
            assert exc.code == 0
    assert "status:         ready" in capsys.readouterr().out


def test_ready_cli_not_ready() -> None:
    payload = {"status": "not_ready", "twin": None, "hasDriftReport": False}
    with patch("urllib.request.urlopen", return_value=_Resp(payload)):
        try:
            main(["ready"])
        except SystemExit as exc:
            assert exc.code == 1
