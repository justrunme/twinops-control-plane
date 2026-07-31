"""Tests for twinopsctl proposal."""

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


def test_proposal_cli(capsys) -> None:
    payload = {
        "metadata": {"name": "assembly-line-a"},
        "status": {"applied": True, "changes": 2, "overlayPath": "/tmp/overlay.usda"},
    }
    with patch("urllib.request.urlopen", return_value=_Resp(payload)):
        try:
            main(["proposal"])
        except SystemExit as exc:
            assert exc.code == 0
    out = capsys.readouterr().out
    assert "applied: True" in out
    assert "changes: 2" in out
