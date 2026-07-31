"""Generic File + REST PLM adapters."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from twinops.plm.base import PlmAdapter
from twinops.plm.file import FilePlmAdapter
from twinops.plm.rest import RestPlmAdapter

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "examples" / "assembly-line" / "plm-catalog.json"


def test_file_adapter_is_plm_adapter() -> None:
    adapter = FilePlmAdapter.from_catalog(CATALOG)
    assert isinstance(adapter, PlmAdapter)
    assert adapter.provider == "file"
    assert adapter.get("1004711") is not None


def test_rest_adapter_get_and_list() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    store = {
        str(item["itemId"]): {
            "id": item["itemId"],
            "revision": item["revision"],
            "lifecycle": item["lifecycle"],
            "metadata": {"prim": item["prim"], "name": item.get("name", "")},
        }
        for item in catalog["items"]
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
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

        def do_PUT(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            item_id = self.path.rsplit("/", 1)[-1]
            store[item_id] = payload
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        adapter = RestPlmAdapter(base)
        assert isinstance(adapter, PlmAdapter)
        items = adapter.items
        assert items
        first = items[0]
        got = adapter.get(first.item_id)
        assert got is not None
        assert got.revision == first.revision
        bumped = adapter.bump_revision(first.item_id)
        assert bumped.revision != first.revision
    finally:
        server.shutdown()
