import json
from pathlib import Path

from twinops.plm.mock import MockPlmAdapter, PlmItem, ensure_catalog_from_manifest
from twinops.schema import load_manifest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def test_catalog_roundtrip_and_compare(tmp_path: Path) -> None:
    catalog = tmp_path / "plm-catalog.json"
    ensure_catalog_from_manifest(EXAMPLE / "twin.yaml", catalog)
    adapter = MockPlmAdapter.from_catalog(catalog)
    assert len(adapter.items) == 4

    manifest = load_manifest(EXAMPLE / "twin.yaml")
    diffs = adapter.compare_manifest(manifest)
    assert all(item["status"] == "SYNCED" for item in diffs)

    bumped = adapter.bump_revision("1004711")
    assert bumped.revision == "D"
    adapter.write_catalog(catalog)
    diffs = adapter.compare_manifest(manifest)
    robot = next(item for item in diffs if item["itemId"] == "1004711")
    assert robot["status"] == "DRIFT"
    assert robot["catalogRevision"] == "D"


def test_sync_manifest_updates_revision(tmp_path: Path) -> None:
    example = tmp_path / "line"
    example.mkdir()
    twin = example / "twin.yaml"
    twin.write_text((EXAMPLE / "twin.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    # Copy assets reference is relative — load_manifest resolves base stage.
    # Point baseStage to absolute sample asset to keep loader happy.
    text = twin.read_text(encoding="utf-8")
    text = text.replace(
        "baseStage: assets/root.usda",
        f"baseStage: {EXAMPLE / 'assets' / 'root.usda'}",
    )
    twin.write_text(text, encoding="utf-8")

    catalog = example / "plm-catalog.json"
    adapter = MockPlmAdapter(
        [
            PlmItem(
                item_id="1004711",
                revision="E",
                lifecycle="Released",
                prim="/World/Factory/LineA/Robot01",
            )
        ]
    )
    adapter.write_catalog(catalog)
    report = adapter.sync_manifest(twin, write=True)
    assert report["changed"][0]["to"] == "E"
    data = json.loads(
        # re-read via yaml through adapter compare
        Path(catalog).read_text(encoding="utf-8")
    )
    assert data["items"][0]["revision"] == "E"
    manifest = load_manifest(twin)
    assert manifest.plm_mappings[0].revision == "E"


def test_desired_fragment_contains_plm_attrs() -> None:
    adapter = MockPlmAdapter.from_catalog(EXAMPLE / "plm-catalog.json")
    fragment = adapter.desired_fragment()
    assert fragment["kind"] == "DesiredState"
    assert fragment["spec"]["resources"][0]["attributes"]["twinops:plmRevision"]
