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


def test_plm_mapping_omitted_revision_lifecycle_track_latest(tmp_path: Path) -> None:
    path = tmp_path / "track.yaml"
    path.write_text(
        """
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: track
spec:
  source:
    baseStage: root.usda
  plm:
    mappings:
      - itemId: "1004711"
        prim: /World/Factory/LineA/Robot01
""",
        encoding="utf-8",
    )
    # base stage file required by resolve only; create stub so load succeeds
    (tmp_path / "root.usda").write_text("#usda 1.0\n", encoding="utf-8")
    manifest = load_manifest(path)
    assert len(manifest.plm_mappings) == 1
    m = manifest.plm_mappings[0]
    assert m.revision is None
    assert m.lifecycle is None
    # Critical: omitted pin must not become the catalog-looking sentinel "A"/"Released".
    assert m.revision != "A"
    assert m.lifecycle != "Released"


def test_plm_mapping_explicit_null_track_latest(tmp_path: Path) -> None:
    path = tmp_path / "null.yaml"
    path.write_text(
        """
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: track
spec:
  source:
    baseStage: root.usda
  plm:
    mappings:
      - itemId: "1"
        prim: /World/Factory/LineA/Robot01
        revision: null
        lifecycle: null
""",
        encoding="utf-8",
    )
    (tmp_path / "root.usda").write_text("#usda 1.0\n", encoding="utf-8")
    m = load_manifest(path).plm_mappings[0]
    assert m.revision is None
    assert m.lifecycle is None


def test_plm_mapping_empty_revision_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text(
        """
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: bad
spec:
  source:
    baseStage: root.usda
  plm:
    mappings:
      - itemId: "1"
        prim: /World/Factory/LineA/Robot01
        revision: ""
""",
        encoding="utf-8",
    )
    (tmp_path / "root.usda").write_text("#usda 1.0\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="revision"):
        load_manifest(path)


def test_plm_mapping_pinned_revision_preserved(tmp_path: Path) -> None:
    path = tmp_path / "pinned.yaml"
    path.write_text(
        """
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: pinned
spec:
  source:
    baseStage: root.usda
  plm:
    mappings:
      - itemId: "1"
        prim: /World/Factory/LineA/Robot01
        revision: "A"
        lifecycle: Released
""",
        encoding="utf-8",
    )
    (tmp_path / "root.usda").write_text("#usda 1.0\n", encoding="utf-8")
    m = load_manifest(path).plm_mappings[0]
    assert m.revision == "A"
    assert m.lifecycle == "Released"
