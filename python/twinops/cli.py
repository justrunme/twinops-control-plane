"""twinopsctl — CLI for the TwinOps Digital Twin Compiler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from twinops import __version__
from twinops.composer import compose_digital_twin
from twinops.schema import ManifestError, load_manifest


def _cmd_build(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output = Path(args.out) if args.out else Path("usd/generated") / manifest.name
    result = compose_digital_twin(manifest, output, copy_base_stage=not args.no_copy_base)

    print(f"TwinOps composed digital twin '{manifest.name}'")
    print(f"  output: {result.output_dir}")
    for key in ("root", "plm_overlay", "telemetry_overlay", "variant_overlay", "report"):
        path = result.files.get(key)
        if path:
            print(f"  {key}: {path}")

    for issue in result.issues:
        prefix = issue.severity.upper()
        print(f"  [{prefix}] {issue.code}: {issue.message}")

    if args.json:
        print(json.dumps(result.report, indent=2))

    return 0 if result.ok else 1


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"twinopsctl {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="twinopsctl",
        description="TwinOps CLI — GitOps toolkit for industrial digital twins",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")

    sub = parser.add_subparsers(dest="command")

    build = sub.add_parser("build", help="compose OpenUSD layers from a DigitalTwin manifest")
    build.add_argument("manifest", help="path to DigitalTwin YAML manifest")
    build.add_argument(
        "--out",
        default=None,
        help="output directory (default: usd/generated/<name>)",
    )
    build.add_argument(
        "--no-copy-base",
        action="store_true",
        help="do not copy the base stage into the output directory",
    )
    build.add_argument(
        "--json",
        action="store_true",
        help="print reconciliation report JSON to stdout",
    )
    build.set_defaults(func=_cmd_build)

    version = sub.add_parser("version", help="print version")
    version.set_defaults(func=_cmd_version)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "version", False) and not args.command:
        raise SystemExit(_cmd_version(args))

    if not args.command:
        parser.print_help()
        raise SystemExit(2)

    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
