"""Tests for twinopsctl scene --from-url."""

from __future__ import annotations

import json
from unittest.mock import patch

from twinops.cli import main
from twinops.scene import build_scene_snapshot


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


def test_scene_from_url_strict(capsys) -> None:
    scene = build_scene_snapshot(
        twin_name="assembly-line-a",
        findings=[
            {
                "prim": "/World/Factory/LineA/Robot01",
                "attribute": "twinops:temperature",
                "status": "CRITICAL",
                "severity": "critical",
                "message": "hot",
            }
        ],
    )
    with patch("urllib.request.urlopen", return_value=_Resp(scene)):
        try:
            main(["scene", "--from-url", "http://127.0.0.1:8080", "--strict"])
        except SystemExit as exc:
            assert exc.code == 1
    assert "HIGHLIGHT" in capsys.readouterr().out
