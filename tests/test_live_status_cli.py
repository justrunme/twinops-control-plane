"""Tests for twinopsctl live status."""

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


def test_live_status_cli(capsys) -> None:
    responses = [
        _Resp({"status": "ok", "version": "0.3.6"}),
        _Resp(
            {
                "status": "ready",
                "twin": "assembly-line-a",
                "hasDriftReport": True,
            }
        ),
        _Resp(
            {
                "hasDrift": False,
                "highlightedPrims": 0,
                "timelineEvents": 2,
            }
        ),
    ]

    def _open(*_args, **_kwargs):
        return responses.pop(0)

    with patch("urllib.request.urlopen", side_effect=_open):
        try:
            main(["live", "status"])
        except SystemExit as exc:
            assert exc.code == 0
    out = capsys.readouterr().out
    assert "health:  ok" in out
    assert "ready:   ready" in out
    assert "hasDrift=False" in out
