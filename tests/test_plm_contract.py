"""Contract tests — File and REST PLM adapters are interchangeable."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from twinops.plm.file import FilePlmAdapter
from twinops.plm.rest import RestPlmAdapter

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "examples" / "assembly-line" / "plm-catalog.json"


@pytest.fixture(scope="module")
def catalog_items() -> list[dict]:
    return list(json.loads(CATALOG.read_text(encoding="utf-8"))["items"])


@pytest.fixture()
def file_adapter() -> FilePlmAdapter:
    return FilePlmAdapter.from_catalog(CATALOG)


@pytest.fixture()
def rest_adapter(catalog_items: list[dict]):
    store = {
        str(item["itemId"]): {
            "id": item["itemId"],
            "revision": item["revision"],
            "lifecycle": item["lifecycle"],
            "metadata": {"prim": item["prim"], "name": item.get("name", "")},
        }
        for item in catalog_items
    }
    force_errors: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            if force_errors.get("mode") == "timeout":
                return
            if force_errors.get("mode") == "auth":
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error":"unauthorized"}')
                return
            if force_errors.get("mode") == "malformed":
                body = b"not-json"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.rstrip("/") == "/items":
                body = json.dumps(list(store.values())).encode("utf-8")
            elif self.path.startswith("/items/"):
                item_id = self.path.rsplit("/", 1)[-1]
                if item_id not in store:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(store[item_id]).encode("utf-8")
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    adapter = RestPlmAdapter(base, timeout=0.5)
    try:
        yield adapter, force_errors
    finally:
        server.shutdown()


def test_get_item_revision_lifecycle(file_adapter, rest_adapter) -> None:
    rest, _errors = rest_adapter
    for adapter in (file_adapter, rest):
        item = adapter.get("1004711")
        assert item is not None
        assert item.revision
        assert item.lifecycle
        assert item.prim


def test_not_found(file_adapter, rest_adapter) -> None:
    rest, _errors = rest_adapter
    assert file_adapter.get("missing-item") is None
    assert rest.get("missing-item") is None


def test_rest_timeout(rest_adapter) -> None:
    rest, errors = rest_adapter
    errors["mode"] = "timeout"
    with pytest.raises(RuntimeError):
        rest.get("1004711")


def test_rest_malformed(rest_adapter) -> None:
    rest, errors = rest_adapter
    errors["mode"] = "malformed"
    with pytest.raises((RuntimeError, ValueError, json.JSONDecodeError)):
        rest.get("1004711")


def test_rest_auth_failure(rest_adapter) -> None:
    rest, errors = rest_adapter
    errors["mode"] = "auth"
    with pytest.raises(RuntimeError) as exc:
        rest.get("1004711")
    assert "401" in str(exc.value)


def test_file_and_rest_same_catalog_shape(file_adapter, rest_adapter) -> None:
    rest, _errors = rest_adapter
    file_ids = {item.item_id: item.revision for item in file_adapter.items}
    rest_ids = {item.item_id: item.revision for item in rest.items}
    assert file_ids == rest_ids
