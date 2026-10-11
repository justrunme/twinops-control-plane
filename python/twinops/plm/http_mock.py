"""In-process mock PLM HTTP server for contract and E2E tests.

Supports:
- GET /items, GET /items/{id} with ETag / If-None-Match → 304
- PUT /items/{id} with If-Match → 409 on version conflict
- Forced faults: auth (401), 5xx, timeout
- Revision bumps that advance the catalog ETag
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import unquote


def _item_doc(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or item.get("itemId")),
        "revision": str(item.get("revision") or "A"),
        "lifecycle": str(item.get("lifecycle") or "Released"),
        "metadata": {
            "prim": str(item.get("prim") or (item.get("metadata") or {}).get("prim") or ""),
            "name": str(item.get("name") or (item.get("metadata") or {}).get("name") or ""),
        },
        "version": int(item.get("version") or 1),
    }


class MockPlmHTTPServer:
    """Thread-backed HTTP PLM mock with revision/ETag semantics."""

    def __init__(
        self,
        items: list[dict[str, Any]],
        *,
        token: str | None = "test-token",
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self.token = token
        self._lock = threading.RLock()
        self._store: dict[str, dict[str, Any]] = {}
        for raw in items:
            doc = _item_doc(raw)
            self._store[doc["id"]] = doc
        self._fault: str | None = None
        self._generation = 1
        self._put_count = 0
        self._get_count = 0

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

            def _auth_ok(self) -> bool:
                if outer.token is None:
                    return True
                header = self.headers.get("Authorization", "")
                return header == f"Bearer {outer.token}"

            def _send(self, code: int, body: bytes = b"", *, etag: str | None = None) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                if etag:
                    self.send_header("ETag", etag)
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                with outer._lock:
                    outer._get_count += 1
                    fault = outer._fault
                    if fault == "timeout":
                        time.sleep(30)
                        return
                    if fault == "auth" or not self._auth_ok():
                        self._send(401, b'{"error":"unauthorized"}')
                        return
                    if fault == "5xx":
                        self._send(503, b'{"error":"unavailable"}')
                        return
                    etag = outer.etag()
                    inm = self.headers.get("If-None-Match")
                    if inm and inm.strip() == etag:
                        self._send(304, etag=etag)
                        return
                    path = self.path.split("?", 1)[0].rstrip("/") or "/"
                    if path == "/items":
                        body = json.dumps({"items": list(outer._store.values())}).encode("utf-8")
                        self._send(200, body, etag=etag)
                        return
                    if path.startswith("/items/"):
                        item_id = unquote(path.rsplit("/", 1)[-1])
                        item = outer._store.get(item_id)
                        if item is None:
                            self._send(404, b'{"error":"not found"}')
                            return
                        body = json.dumps(item).encode("utf-8")
                        self._send(200, body, etag=outer._item_etag(item))
                        return
                    self._send(404, b'{"error":"not found"}')

            def do_PUT(self) -> None:  # noqa: N802
                with outer._lock:
                    outer._put_count += 1
                    fault = outer._fault
                    if fault == "timeout":
                        time.sleep(30)
                        return
                    if fault == "auth" or not self._auth_ok():
                        self._send(401, b'{"error":"unauthorized"}')
                        return
                    if fault == "5xx":
                        self._send(503, b'{"error":"unavailable"}')
                        return
                    path = self.path.split("?", 1)[0]
                    if not path.startswith("/items/"):
                        self._send(404, b'{"error":"not found"}')
                        return
                    item_id = unquote(path.rstrip("/").rsplit("/", 1)[-1])
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    current = outer._store.get(item_id)
                    if_match = self.headers.get("If-Match")
                    if current is not None and if_match:
                        expected = if_match.strip()
                        current_etag = outer._item_etag(current)
                        if expected not in {current_etag, str(current.get("version"))}:
                            body = json.dumps(
                                {
                                    "error": "version conflict",
                                    "itemId": item_id,
                                    "currentVersion": current.get("version"),
                                    "etag": outer.etag(),
                                }
                            ).encode("utf-8")
                            self._send(409, body, etag=outer.etag())
                            return
                    doc = _item_doc({**payload, "id": item_id})
                    if current is not None:
                        doc["version"] = int(current.get("version") or 1) + 1
                    outer._store[item_id] = doc
                    outer._generation += 1
                    body = json.dumps(doc).encode("utf-8")
                    self._send(200, body, etag=outer.etag())

        self._httpd = HTTPServer((host, port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._started = False

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def get_count(self) -> int:
        with self._lock:
            return self._get_count

    @property
    def put_count(self) -> int:
        with self._lock:
            return self._put_count

    def start(self) -> MockPlmHTTPServer:
        if not self._started:
            self._thread.start()
            self._started = True
        return self

    def stop(self) -> None:
        if self._started:
            self._httpd.shutdown()
            self._thread.join(timeout=2)
            self._started = False

    def __enter__(self) -> MockPlmHTTPServer:
        return self.start()

    def __exit__(self, *args: object) -> None:
        self.stop()

    def etag(self) -> str:
        with self._lock:
            payload = json.dumps(
                sorted(
                    (item_id, item["revision"], item.get("version", 1))
                    for item_id, item in self._store.items()
                ),
                separators=(",", ":"),
            )
            digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
            return f'W/"plm-{self._generation}-{digest}"'

    @staticmethod
    def _item_etag(item: dict[str, Any]) -> str:
        return f'W/"item-{item["id"]}-v{item.get("version", 1)}"'

    def set_fault(self, mode: str | None) -> None:
        """Force auth | timeout | 5xx | None (clear)."""
        with self._lock:
            self._fault = mode

    def bump(self, item_id: str, *, to: str | None = None) -> dict[str, Any]:
        with self._lock:
            current = self._store.get(item_id)
            if current is None:
                raise KeyError(item_id)
            rev = current["revision"]
            if to is None:
                if len(rev) == 1 and rev.isalpha():
                    to = chr(ord(rev.upper()) + 1)
                else:
                    to = f"{rev}+"
            current = dict(current)
            current["revision"] = to
            current["version"] = int(current.get("version") or 1) + 1
            self._store[item_id] = current
            self._generation += 1
            return dict(current)

    def items(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._store.values()]
