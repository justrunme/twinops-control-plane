"""Negative tests for PLM SSRF-adjacent fail-closed + fingerprint + bump ETag."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from twinops.plm.errors import PlmAuthError
from twinops.plm.http_mock import MockPlmHTTPServer
from twinops.plm.rest import RestPlmAdapter, _normalize_item
from twinops.plm.sync import revision_fingerprint
from twinops.plm.mock import PlmItem


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


def test_auth_error_omits_response_body(catalog_items=None) -> None:
    items = [{"id": "1", "revision": "A", "lifecycle": "Released"}]
    with MockPlmHTTPServer(items, token="secret") as server:
        adapter = RestPlmAdapter(server.url, token="wrong", timeout=1.0, max_retries=1)
        with pytest.raises(PlmAuthError) as exc:
            adapter.fetch_catalog()
        assert "auth_failed" in str(exc.value)
        assert "unauthorized" not in str(exc.value).lower() or "HTTP 401" in str(exc.value)


def test_bump_revision_requires_item_etag() -> None:
    items = [{"id": "1004711", "revision": "A", "lifecycle": "Released", "prim": "/P"}]
    with MockPlmHTTPServer(items, token="tok") as server:
        adapter = RestPlmAdapter(server.url, token="tok", timeout=1.0, max_retries=1)
        # get() populates last_item_etag from item response
        got = adapter.get("1004711")
        assert got is not None
        assert adapter.last_item_etag
        bumped = adapter.bump_revision("1004711")
        assert bumped.revision != "A"


def test_bump_revision_refuses_without_etag(monkeypatch) -> None:
    items = [{"id": "1004711", "revision": "A", "lifecycle": "Released"}]
    with MockPlmHTTPServer(items, token="tok") as server:
        adapter = RestPlmAdapter(server.url, token="tok", timeout=1.0, max_retries=1)

        def _get(item_id: str):
            adapter.last_item_etag = None
            return PlmItem(item_id=item_id, revision="A", lifecycle="Released", prim="", name="")

        monkeypatch.setattr(adapter, "get", _get)
        with pytest.raises(ValueError, match="item ETag required"):
            adapter.bump_revision("1004711")
