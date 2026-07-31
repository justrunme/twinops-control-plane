"""Tests for twinopsctl doctor CLI."""

from __future__ import annotations

import json
from unittest.mock import patch

from twinops.cli import main
from twinops.doctor import Check


def test_doctor_json_stdout_only(capsys) -> None:
    checks = [
        Check(name="python:yaml", ok=True, required=True, detail="ok"),
        Check(name="mqtt-topic-catalog", ok=True, required=True, detail="synced"),
    ]
    with patch("twinops.cli.run_doctor", return_value=checks):
        try:
            main(["doctor", "--json"])
        except SystemExit as exc:
            assert exc.code == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["checks"][0]["name"] == "python:yaml"
    assert "environment looks ready" not in captured.out
