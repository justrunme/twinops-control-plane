from pathlib import Path

import pytest
from twinops.schema import ManifestError, load_manifest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line" / "twin.yaml"


def test_load_assembly_line_manifest() -> None:
    manifest = load_manifest(EXAMPLE)
    assert manifest.name == "assembly-line-a"
    assert manifest.variant == "high-throughput"
    assert len(manifest.plm_mappings) == 4
    assert len(manifest.telemetry_mappings) == 5
    assert manifest.resolve_base_stage().name == "root.usda"


def test_reject_bad_prim(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: bad
spec:
  source:
    baseStage: missing.usda
  plm:
    mappings:
      - itemId: "1"
        prim: World/Robot
""",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError):
        load_manifest(path)
