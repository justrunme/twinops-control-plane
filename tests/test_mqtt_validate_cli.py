"""Tests for twinopsctl mqtt validate."""

from __future__ import annotations

import json
from pathlib import Path

from twinops.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line" / "mqtt-payload.example.json"


def test_mqtt_validate_cli(capsys) -> None:
    try:
        main(["mqtt", "validate", str(EXAMPLE), "--json"])
    except SystemExit as exc:
        assert exc.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
