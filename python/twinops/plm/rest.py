"""Generic REST PLM adapter with ETag polling and retry/backoff.

Expected endpoints (relative to base URL):

- ``GET /items`` → list or ``{ "items": [...] }`` (ETag / If-None-Match)
- ``GET /items/{id}`` → single item
- ``PUT /items/{id}`` → optional write for revision bump (If-Match → 409)

Item JSON (either shape accepted):

```json
{ "id": "1004711", "revision": "B", "lifecycle": "Released",
  "metadata": { "prim": "/World/Robot", "name": "Robot" } }
```

or TwinOps catalog fields: ``itemId``, ``revision``, ``lifecycle``, ``prim``, ``name``.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

from twinops.plm.errors import (
    PlmAuthError,
    PlmConflictError,
    PlmNotModified,
    PlmTransientError,
)
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


@dataclass(frozen=True)
class CatalogFetch:
    items: list[PlmItem]
    etag: str | None
    not_modified: bool = False


class RestPlmAdapter:
    """HTTP PLM backend — no vendor SDK required."""

    provider = "rest"

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 5.0,
        max_retries: int = 4,
        backoff_base: float = 0.05,
        backoff_cap: float = 2.0,
        jitter: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.jitter = jitter
        self.last_etag: str | None = None
        self.request_count = 0
        self.retry_count = 0

    def _headers(self, *, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if extra:
            headers.update(extra)
        return headers

    def _sleep_backoff(self, attempt: int) -> None:
        exp = min(self.backoff_cap, self.backoff_base * (2**attempt))
        delay = random.uniform(0, exp) if self.jitter else exp
        if delay > 0:
            time.sleep(delay)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        retry: bool = True,
    ) -> tuple[Any, dict[str, str], int]:
        url = urljoin(self.base_url, path.lstrip("/"))
        data = None if body is None else json.dumps(body).encode("utf-8")
        attempts = self.max_retries if retry else 1
        last_exc: Exception | None = None

        for attempt in range(attempts):
            self.request_count += 1
            req = urllib.request.Request(
                url, data=data, headers=self._headers(extra=extra_headers), method=method
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    headers = {k: v for k, v in resp.headers.items()}
                    code = getattr(resp, "status", 200) or 200
                    if not raw:
                        return None, headers, code
                    return json.loads(raw.decode("utf-8")), headers, code
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code in {401, 403}:
                    raise PlmAuthError(
                        f"PLM REST {method} {url} → HTTP {exc.code}: {detail}"
                    ) from exc
                if exc.code == 409:
                    etag = exc.headers.get("ETag") if exc.headers else None
                    raise PlmConflictError(
                        f"PLM REST {method} {url} → HTTP 409: {detail}",
                        etag=etag,
                    ) from exc
                if exc.code == 304:
                    etag = exc.headers.get("ETag") if exc.headers else None
                    raise PlmNotModified(etag or "") from exc
                if exc.code >= 500:
                    last_exc = PlmTransientError(
                        f"PLM REST {method} {url} → HTTP {exc.code}: {detail}"
                    )
                    if attempt + 1 < attempts:
                        self.retry_count += 1
                        self._sleep_backoff(attempt)
                        continue
                    raise last_exc from exc
                raise RuntimeError(
                    f"PLM REST {method} {url} → HTTP {exc.code}: {detail}"
                ) from exc
            except urllib.error.URLError as exc:
                last_exc = PlmTransientError(
                    f"PLM REST {method} {url} failed: {exc.reason}"
                )
            except TimeoutError as exc:
                last_exc = PlmTransientError(f"PLM REST {method} {url} timed out")
                last_exc.__cause__ = exc
            except RemoteDisconnected as exc:
                last_exc = PlmTransientError(f"PLM REST {method} {url} failed: {exc}")
                last_exc.__cause__ = exc
            except json.JSONDecodeError as exc:
                raise ValueError(f"PLM REST {method} {url} returned invalid JSON") from exc

            if attempt + 1 < attempts:
                self.retry_count += 1
                self._sleep_backoff(attempt)
                continue
            assert last_exc is not None
            raise last_exc

        assert last_exc is not None
        raise last_exc

    def fetch_catalog(self, *, if_none_match: str | None = None) -> CatalogFetch:
        """GET /items with optional If-None-Match. Raises PlmNotModified on 304."""
        extra = {}
        if if_none_match:
            extra["If-None-Match"] = if_none_match
        try:
            data, headers, _code = self._request("GET", "items", extra_headers=extra or None)
        except PlmNotModified as exc:
            etag = str(exc) or if_none_match
            self.last_etag = etag
            raise PlmNotModified(etag or "") from exc

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
        items = sorted(items, key=lambda item: item.item_id)
        etag = headers.get("ETag") or headers.get("Etag")
        self.last_etag = etag
        return CatalogFetch(items=items, etag=etag, not_modified=False)

    def get(self, item_id: str) -> PlmItem | None:
        try:
            data, _headers, _code = self._request(
                "GET", f"items/{quote(item_id, safe='')}"
            )
        except PlmAuthError:
            raise
        except PlmTransientError:
            raise
        except PlmConflictError:
            raise
        except RuntimeError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        if not isinstance(data, dict):
            raise ValueError("GET /items/{id} must return an object")
        return _normalize_item(data)

    @property
    def items(self) -> list[PlmItem]:
        return self.fetch_catalog().items

    def bump_revision(
        self,
        item_id: str,
        *,
        to: str | None = None,
        if_match: str | None = None,
    ) -> PlmItem:
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
        extra = {}
        match = if_match if if_match is not None else self.last_etag
        if match:
            extra["If-Match"] = match
        self._request(
            "PUT",
            f"items/{quote(item_id, safe='')}",
            body=_item_payload(updated),
            extra_headers=extra or None,
            retry=False,
        )
        return updated

    def _local(self) -> MockPlmAdapter:
        return MockPlmAdapter(self.items)

    def compare_manifest(self, manifest: DigitalTwinManifest) -> list[dict[str, Any]]:
        return self._local().compare_manifest(manifest)

    def sync_manifest(self, manifest_path: str | Path, *, write: bool = True) -> dict[str, Any]:
        report = self._local().sync_manifest(manifest_path, write=write)
        report["provider"] = self.provider
        if self.last_etag:
            report["etag"] = self.last_etag
        return report

    def desired_fragment(self) -> dict[str, Any]:
        return self._local().desired_fragment()
