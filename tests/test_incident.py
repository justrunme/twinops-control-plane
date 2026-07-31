"""Tests for TwinIncident export and replay."""

from __future__ import annotations

import json
from pathlib import Path

from twinops.cli import main
from twinops.incident.record import timeline_to_incident
from twinops.incident.replay import replay_incident

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def test_timeline_to_incident_orders_chronologically() -> None:
    timeline = [
        {
            "timestamp": "2026-07-31T10:43:00Z",
            "type": "spike",
            "summary": "hot",
            "payload": {},
        },
        {
            "timestamp": "2026-07-31T10:41:00Z",
            "type": "telemetry",
            "summary": "ok",
            "payload": {},
        },
    ]
    record = timeline_to_incident(timeline, twin="assembly-line-a")
    assert record.steps[0].at.startswith("2026-07-31T10:41")
    assert record.steps[-1].kind == "spike"


def test_export_and_replay_sample(tmp_path: Path) -> None:
    incident = EXAMPLE / "incident-heat-spike.json"
    # Need a composed stage for replay.
    stage = EXAMPLE / "generated" / "root.usda"
    if not stage.is_file():
        from twinops.composer.compose import compose_digital_twin
        from twinops.schema.manifest import load_manifest

        manifest = load_manifest(EXAMPLE / "twin.yaml")
        out = tmp_path / "stage"
        result = compose_digital_twin(manifest, out)
        assert result.ok
        stage = result.files["root"]

    result = replay_incident(
        incident,
        desired=EXAMPLE / "desired.yaml",
        stage=stage,
        observed=EXAMPLE / "telemetry.json",
        manifest=EXAMPLE / "twin.yaml",
    )
    assert result.steps_played == 6
    assert len(result.ticks) == 6
    assert any(tick.get("hasDrift") for tick in result.ticks)


def test_incident_export_cli(tmp_path: Path, capsys) -> None:
    timeline = tmp_path / "timeline.json"
    timeline.write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-07-31T10:00:00Z",
                    "type": "telemetry",
                    "summary": "ok",
                    "payload": {},
                }
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "incident.json"
    try:
        main(["incident", "export", "--timeline", str(timeline), "--out", str(out)])
    except SystemExit as exc:
        assert exc.code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["kind"] == "TwinIncident"
    assert len(data["spec"]["steps"]) == 1
