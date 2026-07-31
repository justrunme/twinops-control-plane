import json
from pathlib import Path

from twinops.composer import compose_digital_twin
from twinops.drift.engine import detect_drift
from twinops.drift.html_report import write_html_report
from twinops.drift.reconcile import propose_reconciliation
from twinops.drift.table import render_drift_table
from twinops.schema import load_manifest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def _stale_stage(tmp_path: Path) -> Path:
    manifest = load_manifest(EXAMPLE / "twin.yaml")
    result = compose_digital_twin(manifest, tmp_path / "stage")
    plm = result.files["plm_overlay"]
    text = plm.read_text(encoding="utf-8")
    text = text.replace(
        'over "Robot01"',
        'over "Robot01"',
        1,
    )
    # Force Robot01 revision to B for drift.
    parts = text.split('over "Robot01"')
    assert len(parts) == 2
    robot_block, rest_tail = parts[1], ""
    # parts[1] contains from Robot01 to EOF; rewrite first plmRevision in that section.
    robot_block = robot_block.replace(
        'twinops:plmRevision = "C"',
        'twinops:plmRevision = "B"',
        1,
    )
    plm.write_text(parts[0] + 'over "Robot01"' + robot_block + rest_tail, encoding="utf-8")
    return result.files["root"]


def test_detect_drift_assembly_line(tmp_path: Path) -> None:
    stage = _stale_stage(tmp_path)
    report = detect_drift(
        desired=EXAMPLE / "desired.yaml",
        stage=stage,
        observed=EXAMPLE / "telemetry.json",
        manifest=EXAMPLE / "twin.yaml",
    )

    assert report.has_drift
    statuses = {f.status for f in report.findings}
    assert "DRIFT" in statuses
    assert "CRITICAL" in statuses
    assert "MISSING" in statuses

    robot_rev = next(
        f
        for f in report.findings
        if f.prim.endswith("Robot01") and f.attribute == "twinops:plmRevision"
    )
    assert robot_rev.desired == "C"
    assert robot_rev.rendered == "B"
    assert robot_rev.status == "DRIFT"

    firmware = next(
        f
        for f in report.findings
        if f.prim.endswith("Robot01") and f.attribute == "twinops:firmware"
    )
    assert firmware.desired == "4.14"
    assert firmware.observed == "4.12"

    table = render_drift_table(report)
    assert "DRIFT DETECTED" in table
    assert "Robot01" in table

    html_path = write_html_report(report, tmp_path / "drift-report.html")
    html = html_path.read_text(encoding="utf-8")
    assert "DRIFT DETECTED" in html
    assert "Robot01" in html

    proposal = propose_reconciliation(report, tmp_path / "proposal")
    assert proposal.overlay_path.is_file()
    overlay = proposal.overlay_path.read_text(encoding="utf-8")
    assert "plmRevision" in overlay or "twinops:plmRevision" in overlay
    assert "maintenance" in overlay
    assert proposal.summary_path.is_file()
    assert "TwinOps reconciliation" in proposal.summary_path.read_text(encoding="utf-8")


def test_cli_drift(tmp_path: Path) -> None:
    from twinops.cli import main

    stage = _stale_stage(tmp_path)
    out = tmp_path / "out"
    try:
        main(
            [
                "drift",
                "--desired",
                str(EXAMPLE / "desired.yaml"),
                "--stage",
                str(stage),
                "--observed",
                str(EXAMPLE / "telemetry.json"),
                "--manifest",
                str(EXAMPLE / "twin.yaml"),
                "--out",
                str(out),
                "--propose",
                str(tmp_path / "proposal"),
            ]
        )
    except SystemExit as exc:
        assert exc.code in {1, 3}

    assert (out / "drift-report.json").is_file()
    payload = json.loads((out / "drift-report.json").read_text(encoding="utf-8"))
    assert payload["status"]["hasDrift"] is True
