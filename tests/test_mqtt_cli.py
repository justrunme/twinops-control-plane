"""Tests for twinopsctl mqtt topics."""

from __future__ import annotations

import json

from twinops.cli import main


def test_mqtt_topics_cli(capsys) -> None:
    try:
        main(["mqtt", "topics"])
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert "factory/robot-01/temperature" in out


def test_mqtt_topics_cli_json(capsys) -> None:
    try:
        main(["mqtt", "topics", "--json"])
    except SystemExit as exc:
        assert exc.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "MqttTopicCatalog"
