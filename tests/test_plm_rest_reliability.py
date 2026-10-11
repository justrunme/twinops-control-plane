"""REST PLM reliability: ETag, backoff, 409, auth, resync."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from twinops.plm.errors import PlmAuthError, PlmConflictError, PlmNotModified, PlmTransientError
from twinops.plm.http_mock import MockPlmHTTPServer
from twinops.plm.rest import RestPlmAdapter
from twinops.plm.sync import PlmSyncSession, compute_backoff
from twinops.schema import load_manifest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "examples" / "assembly-line" / "plm-catalog.json"
TWIN = ROOT / "examples" / "assembly-line" / "twin.yaml"


@pytest.fixture()
def catalog_items() -> list[dict]:
    return list(json.loads(CATALOG.read_text(encoding="utf-8"))["items"])


@pytest.fixture()
def mock_plm(catalog_items):
    with MockPlmHTTPServer(catalog_items, token="test-token") as server:
        yield server


def test_etag_not_modified(mock_plm) -> None:
    adapter = RestPlmAdapter(mock_plm.url, token="test-token", timeout=1.0, max_retries=1)
    first = adapter.fetch_catalog()
    assert first.etag
    assert first.items
    with pytest.raises(PlmNotModified) as exc:
        adapter.fetch_catalog(if_none_match=first.etag)
    assert exc.value.etag == first.etag


def test_revision_change_advances_etag(mock_plm) -> None:
    adapter = RestPlmAdapter(mock_plm.url, token="test-token", timeout=1.0, max_retries=1)
    before = adapter.fetch_catalog()
    mock_plm.bump("1004711")
    after = adapter.fetch_catalog(if_none_match=before.etag)
    assert after.etag != before.etag
    item = next(i for i in after.items if i.item_id == "1004711")
    assert item.revision != next(i for i in before.items if i.item_id == "1004711").revision


def test_auth_failure(mock_plm) -> None:
    adapter = RestPlmAdapter(mock_plm.url, token="wrong", timeout=1.0, max_retries=1)
    with pytest.raises(PlmAuthError):
        adapter.fetch_catalog()


def test_5xx_retries_then_transient(mock_plm) -> None:
    mock_plm.set_fault("5xx")
    adapter = RestPlmAdapter(
        mock_plm.url,
        token="test-token",
        timeout=0.5,
        max_retries=3,
        backoff_base=0.01,
        backoff_cap=0.05,
        jitter=False,
    )
    with pytest.raises(PlmTransientError):
        adapter.fetch_catalog()
    assert adapter.retry_count >= 2


def test_timeout_is_transient(mock_plm) -> None:
    mock_plm.set_fault("timeout")
    adapter = RestPlmAdapter(
        mock_plm.url,
        token="test-token",
        timeout=0.2,
        max_retries=2,
        backoff_base=0.01,
        jitter=False,
    )
    with pytest.raises(PlmTransientError):
        adapter.fetch_catalog()


def test_conflict_on_stale_if_match(mock_plm) -> None:
    adapter = RestPlmAdapter(mock_plm.url, token="test-token", timeout=1.0, max_retries=1)
    adapter.fetch_catalog()
    with pytest.raises(PlmConflictError):
        adapter.bump_revision("1004711", if_match='W/"stale-etag"')


def test_compare_sync_contract(mock_plm, tmp_path: Path) -> None:
    import shutil

    adapter = RestPlmAdapter(mock_plm.url, token="test-token", timeout=1.0)
    example = ROOT / "examples" / "assembly-line"
    shutil.copytree(example / "assets", tmp_path / "assets")
    manifest_path = tmp_path / "twin.yaml"
    manifest_path.write_text(TWIN.read_text(encoding="utf-8"), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    compare = adapter.compare_manifest(manifest)
    assert any(row["status"] == "SYNCED" for row in compare)

    mock_plm.bump("1004711", to="Z")
    compare2 = adapter.compare_manifest(load_manifest(manifest_path))
    drifted = [row for row in compare2 if row["itemId"] == "1004711"][0]
    assert drifted["status"] == "DRIFT"
    assert drifted["catalogRevision"] == "Z"

    report = adapter.sync_manifest(manifest_path, write=True)
    assert report["changed"]
    synced = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    mapping = next(
        m for m in synced["spec"]["plm"]["mappings"] if m["itemId"] == "1004711"
    )
    assert mapping["revision"] == "Z"


def test_resync_exactly_once_after_outage(mock_plm, tmp_path: Path) -> None:
    adapter = RestPlmAdapter(
        mock_plm.url,
        token="test-token",
        timeout=0.5,
        max_retries=1,
        backoff_base=0.01,
        jitter=False,
    )
    manifest_path = tmp_path / "twin.yaml"
    manifest_path.write_text(TWIN.read_text(encoding="utf-8"), encoding="utf-8")
    session = PlmSyncSession(adapter, manifest_path=manifest_path)

    first = session.poll()
    assert first.changed or first.fingerprint
    assert session.resync_count == 0

    mock_plm.set_fault("5xx")
    failed = session.poll()
    assert failed.error
    assert session.in_outage

    mock_plm.set_fault(None)
    recovered = session.poll()
    assert recovered.resynced
    assert session.resync_count == 1

    again = session.poll()
    assert again.not_modified or not again.resynced
    assert session.resync_count == 1


def test_backoff_jitter_bounds() -> None:
    values = [compute_backoff(3, base=0.1, cap=1.0, jitter=True) for _ in range(20)]
    assert all(0 <= v <= 1.0 for v in values)
    fixed = compute_backoff(2, base=0.1, cap=5.0, jitter=False)
    assert fixed == pytest.approx(0.4)
