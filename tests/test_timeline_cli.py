"""Tests for twinopsctl timeline."""

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


def test_timeline_cli(capsys) -> None:
    payload = {
        "items": [
            {
                "id": "1",
                "type": "spike",
                "timestamp": "2026-07-31T00:00:00Z",
                "summary": "heat spike",
            }
        ]
    }
    with patch("urllib.request.urlopen", return_value=_Resp(payload)):
        try:
            main(["timeline", "--limit", "5"])
        except SystemExit as exc:
            assert exc.code == 0
    out = capsys.readouterr().out
    assert "spike" in out
    assert "heat spike" in out
