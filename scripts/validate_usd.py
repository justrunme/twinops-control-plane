#!/usr/bin/env python3
"""Optional OpenUSD validation via Pixar usd-core (pxr).

Usage:
  python scripts/validate_usd.py examples/assembly-line/generated/root.usda
  make usd-validate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate composed USDA with pxr")
    parser.add_argument("stage", type=Path, help="path to root.usda")
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args(argv)

    if not args.stage.is_file():
        print(f"error: stage not found: {args.stage}", file=sys.stderr)
        return 2

    try:
        from pxr import Usd, UsdGeom  # type: ignore
    except ImportError:
        print(
            "error: pxr not installed. pip install 'usd-core' or twinops[usd]",
            file=sys.stderr,
        )
        return 3

    stage = Usd.Stage.Open(str(args.stage))
    if stage is None:
        print(f"error: Usd.Stage.Open failed for {args.stage}", file=sys.stderr)
        return 1

    prims = list(stage.Traverse())
    xforms = [p for p in prims if p.IsA(UsdGeom.Xform)]
    report = {
        "ok": True,
        "stage": str(args.stage),
        "upAxis": UsdGeom.GetStageUpAxis(stage),
        "primCount": len(prims),
        "xformCount": len(xforms),
        "defaultPrim": stage.GetDefaultPrim().GetPath().pathString
        if stage.GetDefaultPrim()
        else None,
        "rootLayer": stage.GetRootLayer().identifier,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"OK {args.stage}: prims={report['primCount']} "
            f"xforms={report['xformCount']} upAxis={report['upAxis']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
