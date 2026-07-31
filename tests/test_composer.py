import json
from pathlib import Path

from twinops.composer import compose_digital_twin
from twinops.composer.usda import discover_variant_names
from twinops.schema import load_manifest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line" / "twin.yaml"
BASE = ROOT / "examples" / "assembly-line" / "assets" / "root.usda"


def test_discover_variants() -> None:
    names = discover_variant_names(BASE.read_text(encoding="utf-8"), "ops")
    assert names == {"nominal", "high-throughput", "maintenance"}


def test_compose_assembly_line(tmp_path: Path) -> None:
    manifest = load_manifest(EXAMPLE)
    result = compose_digital_twin(manifest, tmp_path / "out")

    assert result.ok
    assert (tmp_path / "out" / "root.usda").is_file()
    assert (tmp_path / "out" / "plm-overlay.usda").is_file()
    assert (tmp_path / "out" / "telemetry-overlay.usda").is_file()
    assert (tmp_path / "out" / "variant-overlay.usda").is_file()
    assert (tmp_path / "out" / "assets" / "root.usda").is_file()

    plm = (tmp_path / "out" / "plm-overlay.usda").read_text(encoding="utf-8")
    assert "1004711" in plm
    assert 'twinops:plmRevision = "C"' in plm
    assert "Robot01" in plm

    telemetry = (tmp_path / "out" / "telemetry-overlay.usda").read_text(encoding="utf-8")
    assert "factory/robot-01/temperature" in telemetry
    assert "twinops:temperatureTopic" in telemetry
    assert "twinops:temperature" in telemetry

    variant = (tmp_path / "out" / "variant-overlay.usda").read_text(encoding="utf-8")
    assert 'string ops = "high-throughput"' in variant

    root = (tmp_path / "out" / "root.usda").read_text(encoding="utf-8")
    assert "plm-overlay.usda" in root
    assert "telemetry-overlay.usda" in root
    assert "variant-overlay.usda" in root

    report = json.loads((tmp_path / "out" / "reconciliation-report.json").read_text())
    assert report["metadata"]["name"] == "assembly-line-a"
    assert report["status"]["phase"] in {"Composed", "ComposedWithWarnings"}
    assert report["spec"]["plm"]["mappings"] == 4


def test_cli_build(tmp_path: Path) -> None:
    from twinops.cli import main

    out = tmp_path / "generated"
    try:
        main(["build", str(EXAMPLE), "--out", str(out)])
    except SystemExit as exc:
        assert exc.code == 0

    assert (out / "root.usda").is_file()
    assert (out / "reconciliation-report.json").is_file()
