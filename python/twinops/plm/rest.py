"""Generic REST PLM adapter.

Expected endpoints (relative to base URL):

- ``GET /items`` → list of items
- ``GET /items/{id}`` → single item
- ``PUT /items/{id}`` → optional write for revision bump

Item JSON (either shape accepted):

```json
{ "id": "1004711", "revision": "B", "lifecycle": "Released",
  "metadata": { "prim": "/World/Robot", "name": "Robot" } }
```

or TwinOps catalog fields: ``itemId``, ``revision``, ``lifecycle``, ``prim``, ``name``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

from twinops.plm.mock import MockPlmAdapter, PlmItem
from twinops.schema import DigitalTwinManifest


def _normalize_item(data: dict[str, Any]) -> PlmItem:
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    item_id = str(data.get("id") or data.get("itemId") or "")
    if not item_id:
        raise ValueError("PLM item requires id or itemId")
    prim = str(data.get("prim") or meta.get("prim") or "")
    name = str(data.get("name") or meta.get("name") or "")
    return PlmItem(
        item_id=item_id,
        revision=str(data.get("revision") or "A"),
        lifecycle=str(data.get("lifecycle") or "Released"),
        prim=prim,
        name=name,
    )


def _item_payload(item: PlmItem) -> dict[str, Any]:
    return {
        "id": item.item_id,
        "revision": item.revision,
        "lifecycle": item.lifecycle,
        "metadata": {
            **({"prim": item.prim} if item.prim else {}),
            **({"name": item.name} if item.name else {}),
        },
    }


class RestPlmAdapter:
    """HTTP PLM backend — no vendor SDK required."""

    provider = "rest"

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = urljoin(self.base_url, path.lstrip("/"))
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"PLM REST {method} {url} → HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"PLM REST {method} {url} failed: {exc.reason}") from exc
        if not raw:
            return None
        parsed = json.loads(raw.decode("utf-8"))
        return parsed

    def get(self, item_id: str) -> PlmItem | None:
        try:
            data = self._request("GET", f"items/{quote(item_id, safe='')}")
        except RuntimeError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        if not isinstance(data, dict):
            raise ValueError("GET /items/{id} must return an object")
        return _normalize_item(data)

    @property
    def items(self) -> list[PlmItem]:
        data = self._request("GET", "items")
        if isinstance(data, dict):
            raw_items = data.get("items") or []
        elif isinstance(data, list):
            raw_items = data
        else:
            raise ValueError("GET /items must return a list or {items: [...]}")
        items = [
            _normalize_item(item)
            for item in raw_items
            if isinstance(item, dict)
        ]
        return sorted(items, key=lambda item: item.item_id)

    def bump_revision(self, item_id: str, *, to: str | None = None) -> PlmItem:
        current = self.get(item_id)
        if current is None:
            raise KeyError(f"unknown PLM item: {item_id}")
        if to is None:
            rev = current.revision
            if len(rev) == 1 and rev.isalpha():
                to = chr(ord(rev.upper()) + 1)
            else:
                to = f"{rev}+"
        updated = PlmItem(
            item_id=current.item_id,
            revision=to,
            lifecycle=current.lifecycle,
            prim=current.prim,
            name=current.name,
        )
        self._request("PUT", f"items/{quote(item_id, safe='')}", body=_item_payload(updated))
        return updated

    def _local(self) -> MockPlmAdapter:
        return MockPlmAdapter(self.items)

    def compare_manifest(self, manifest: DigitalTwinManifest) -> list[dict[str, Any]]:
        return self._local().compare_manifest(manifest)

    def sync_manifest(self, manifest_path: str | Path, *, write: bool = True) -> dict[str, Any]:
        report = self._local().sync_manifest(manifest_path, write=write)
        report["provider"] = self.provider
        return report

    def desired_fragment(self) -> dict[str, Any]:
        return self._local().desired_fragment()
