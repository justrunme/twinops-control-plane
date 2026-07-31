"""Tests for twinopsctl metrics."""

from __future__ import annotations

import json
from unittest.mock import patch

from twinops.cli import main


class _Resp:
    def __init__(self, payload: dict | str, status: int = 200) -> None:
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        if isinstance(self._payload, str):
            return self._payload.encode("utf-8")
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_metrics_cli(capsys) -> None:
    payload = {
        "twin": "assembly-line-a",
        "hasDrift": False,
        "summary": {"SYNCED": 4},
        "highlightedPrims": 0,
        "mqttIngestReceived": 0,
        "timelineEvents": 3,
    }
    with patch("urllib.request.urlopen", return_value=_Resp(payload)):
        try:
            main(["metrics"])
        except SystemExit as exc:
            assert exc.code == 0
    out = capsys.readouterr().out
    assert "assembly-line-a" in out
    assert "hasDrift: False" in out


def test_metrics_cli_prometheus(capsys) -> None:
    text = "twinops_drift_has_drift 0\n"
    with patch("urllib.request.urlopen", return_value=_Resp(text)):
        try:
            main(["metrics", "--prometheus"])
        except SystemExit as exc:
            assert exc.code == 0
    assert "twinops_drift_has_drift" in capsys.readouterr().out
