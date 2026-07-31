#!/usr/bin/env python3
"""Sync examples/assembly-line/mqtt-topics.json from the in-code catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from twinops.telemetry.topics import topic_catalog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(ROOT / "examples" / "assembly-line" / "mqtt-topics.json"),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the example JSON differs from the in-code catalog",
    )
    args = parser.parse_args()
    out = Path(args.out)
    catalog = topic_catalog()
    # Drop runtime-only status if present.
    catalog.pop("status", None)
    text = json.dumps(catalog, indent=2) + "\n"
    if args.check:
        current = out.read_text(encoding="utf-8") if out.is_file() else ""
        if current != text:
            print(f"error: {out} is out of sync with twinops.telemetry.topics", file=sys.stderr)
            return 1
        print(f"OK: {out} matches in-code MQTT catalog")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
