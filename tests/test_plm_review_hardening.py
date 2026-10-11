"""Negative tests for PLM fail-closed catalog, fingerprint, and bump ETag."""

from __future__ import annotations

import pytest
from twinops.plm.errors import PlmAuthError
from twinops.plm.http_mock import MockPlmHTTPServer
from twinops.plm.mock import PlmItem
from twinops.plm.rest import RestPlmAdapter, _normalize_item
from twinops.plm.sync import revision_fingerprint


def test_normalize_missing_revision_is_error() -> None:
    with pytest.raises(ValueError, match="missing revision"):
        _normalize_item({"id": "1", "lifecycle": "Released"})


def test_normalize_missing_lifecycle_is_error() -> None:
    with pytest.raises(ValueError, match="missing lifecycle"):
        _normalize_item({"id": "1", "revision": "A"})


def test_fingerprint_includes_lifecycle_and_prim() -> None:
    a = revision_fingerprint(
        [PlmItem(item_id="1", revision="A", lifecycle="Released", prim="/P", name="n")]
    )
    b = revision_fingerprint(
        [PlmItem(item_id="1", revision="A", lifecycle="Obsolete", prim="/P", name="n")]
    )
    c = revision_fingerprint(
        [PlmItem(item_id="1", revision="A", lifecycle="Released", prim="/Q", name="n")]
    )
    assert a != b
    assert a != c


def test_auth_error_omits_response_body() -> None:
    items = [{"id": "1", "revision": "A", "lifecycle": "Released"}]
    with MockPlmHTTPServer(items, token="secret") as server:
        adapter = RestPlmAdapter(server.url, token="wrong", timeout=1.0, max_retries=1)
        with pytest.raises(PlmAuthError) as exc:
            adapter.fetch_catalog()
        assert "auth_failed" in str(exc.value)


def test_bump_revision_requires_item_etag() -> None:
    items = [{"id": "1004711", "revision": "A", "lifecycle": "Released", "prim": "/P"}]
    with MockPlmHTTPServer(items, token="tok") as server:
        adapter = RestPlmAdapter(server.url, token="tok", timeout=1.0, max_retries=1)
        got = adapter.get("1004711")
        assert got is not None
        assert adapter.last_item_etag
        bumped = adapter.bump_revision("1004711")
        assert bumped.revision != "A"


def test_bump_revision_refuses_without_etag(monkeypatch: pytest.MonkeyPatch) -> None:
    items = [{"id": "1004711", "revision": "A", "lifecycle": "Released"}]
    with MockPlmHTTPServer(items, token="tok") as server:
        adapter = RestPlmAdapter(server.url, token="tok", timeout=1.0, max_retries=1)

        def _get(item_id: str) -> PlmItem:
            adapter.last_item_etag = None
            return PlmItem(
                item_id=item_id, revision="A", lifecycle="Released", prim="", name=""
            )

        monkeypatch.setattr(adapter, "get", _get)
        with pytest.raises(ValueError, match="item ETag required"):
            adapter.bump_revision("1004711")


def test_compare_track_latest_does_not_false_match_catalog_A() -> None:
    """Omitted manifest pin (None) must not look like a pinned revision equal to catalog A."""
    from twinops.plm.mock import MockPlmAdapter, PlmItem
    from twinops.schema.manifest import PlmMapping, DigitalTwinManifest

    adapter = MockPlmAdapter(
        [PlmItem(item_id="1", revision="A", lifecycle="Released", prim="/P")]
    )
    manifest = DigitalTwinManifest(
        name="t",
        base_stage="x.usda",
        plm_mappings=[
            PlmMapping(item_id="1", prim="/P", revision=None, lifecycle=None)
        ],
    )
    diffs = adapter.compare_manifest(manifest)
    assert len(diffs) == 1
    assert diffs[0]["status"] == "SYNCED"
    assert diffs[0].get("trackingLatest") is True
    # Still not a false pin equality: manifest revision remains unset.
    assert manifest.plm_mappings[0].revision is None
    assert manifest.plm_mappings[0].revision != "A"


def test_compare_pinned_A_matches_catalog_A() -> None:
    from twinops.plm.mock import MockPlmAdapter, PlmItem
    from twinops.schema.manifest import PlmMapping, DigitalTwinManifest

    adapter = MockPlmAdapter(
        [PlmItem(item_id="1", revision="A", lifecycle="Released", prim="/P")]
    )
    manifest = DigitalTwinManifest(
        name="t",
        base_stage="x.usda",
        plm_mappings=[
            PlmMapping(item_id="1", prim="/P", revision="A", lifecycle="Released")
        ],
    )
    diffs = adapter.compare_manifest(manifest)
    assert diffs[0]["status"] == "SYNCED"
    assert diffs[0].get("trackingLatest") is False


def test_compare_pinned_drift_when_catalog_moves() -> None:
    from twinops.plm.mock import MockPlmAdapter, PlmItem
    from twinops.schema.manifest import PlmMapping, DigitalTwinManifest

    adapter = MockPlmAdapter(
        [PlmItem(item_id="1", revision="B", lifecycle="Released", prim="/P")]
    )
    manifest = DigitalTwinManifest(
        name="t",
        base_stage="x.usda",
        plm_mappings=[
            PlmMapping(item_id="1", prim="/P", revision="A", lifecycle="Released")
        ],
    )
    diffs = adapter.compare_manifest(manifest)
    assert diffs[0]["status"] == "DRIFT"


def test_mock_http_server_is_not_operator_production_import() -> None:
    """Guards against wiring the lab HTTP mock into the operator package path."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    go_files = list((root / "controllers").rglob("*.go")) + list(
        (root / "internal" / "plmsync").rglob("*.go")
    )
    assert go_files, "expected Go operator sources"
    for path in go_files:
        text = path.read_text(encoding="utf-8")
        assert "http_mock" not in text
        assert "MockPlmHTTPServer" not in text
        assert "twinops/plm/mock" not in text
