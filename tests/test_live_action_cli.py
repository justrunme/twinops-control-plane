"""Tests for twinopsctl live spike/reconcile."""

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


def test_live_spike_cli(capsys) -> None:
    payload = {"drift": {"status": {"hasDrift": True, "summary": {"CRITICAL": 1}}}}
    with patch("urllib.request.urlopen", return_value=_Resp(payload)):
        try:
            main(["live", "spike"])
        except SystemExit as exc:
            assert exc.code == 0
    assert "hasDrift=True" in capsys.readouterr().out


def test_live_reconcile_cli(capsys) -> None:
    payload = {
        "changes": 2,
        "drift": {"status": {"hasDrift": False, "summary": {"SYNCED": 4}}},
    }
    with patch("urllib.request.urlopen", return_value=_Resp(payload)):
        try:
            main(["live", "reconcile"])
        except SystemExit as exc:
            assert exc.code == 0
    out = capsys.readouterr().out
    assert "changes=2" in out
    assert "hasDrift=False" in out
