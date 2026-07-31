import argparse
import json
from pathlib import Path

from twinops.cli import _cmd_scene
from twinops.composer import compose_digital_twin
from twinops.drift.engine import detect_drift, save_drift_report
from twinops.schema import load_manifest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def test_scene_cli_from_report(tmp_path: Path, capsys) -> None:
    manifest = load_manifest(EXAMPLE / "twin.yaml")
    composed = compose_digital_twin(manifest, tmp_path / "stage")
    report = detect_drift(
        desired=EXAMPLE / "desired.yaml",
        stage=composed.files["root"],
        observed=EXAMPLE / "telemetry.json",
        manifest=EXAMPLE / "twin.yaml",
    )
    report_path = save_drift_report(report, tmp_path / "drift-report.json")
    out = tmp_path / "scene.json"
    args = argparse.Namespace(
        from_report=str(report_path),
        desired=None,
        stage=None,
        observed=None,
        manifest=None,
        out=str(out),
        json=False,
    )
    assert _cmd_scene(args) == 1
    scene = json.loads(out.read_text(encoding="utf-8"))
    assert scene["protocol"]["name"] == "twinops.highlight.v1"
    assert scene["hasDrift"] is True
    captured = capsys.readouterr().out
    assert "HIGHLIGHT" in captured
