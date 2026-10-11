#!/usr/bin/env python3
"""Long-running mock PLM HTTP server controlled by a JSON command file."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from twinops.plm.http_mock import MockPlmHTTPServer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--token", default="plm-e2e-token")
    parser.add_argument("--meta-out", required=True)
    parser.add_argument("--control", required=True)
    args = parser.parse_args()

    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    items = catalog.get("items") or catalog
    server = MockPlmHTTPServer(items, token=args.token).start()
    meta_path = Path(args.meta_out)
    ctrl_path = Path(args.control)
    meta_path.write_text(
        json.dumps({"url": server.url, "token": args.token}) + "\n",
        encoding="utf-8",
    )
    ctrl_path.write_text(json.dumps({"cmd": "idle"}) + "\n", encoding="utf-8")
    print(json.dumps({"url": server.url}), flush=True)

    while True:
        try:
            cmd = json.loads(ctrl_path.read_text(encoding="utf-8")).get("cmd")
        except (OSError, json.JSONDecodeError):
            cmd = "idle"
        if cmd == "bump":
            server.bump("1004711")
            ctrl_path.write_text(
                json.dumps({"cmd": "idle", "last": "bump", "etag": server.etag()}) + "\n",
                encoding="utf-8",
            )
        elif cmd == "outage":
            server.set_fault("5xx")
            ctrl_path.write_text(
                json.dumps({"cmd": "idle", "last": "outage"}) + "\n",
                encoding="utf-8",
            )
        elif cmd == "recover":
            server.set_fault(None)
            ctrl_path.write_text(
                json.dumps({"cmd": "idle", "last": "recover", "etag": server.etag()})
                + "\n",
                encoding="utf-8",
            )
        elif cmd == "stop":
            server.stop()
            return 0
        time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
