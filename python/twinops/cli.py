"""twinopsctl — CLI for the TwinOps Digital Twin Compiler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from twinops import __version__
from twinops.composer import compose_digital_twin
from twinops.drift.engine import detect_drift, save_drift_report
from twinops.drift.html_report import write_html_report
from twinops.drift.loaders import DriftLoadError
from twinops.drift.reconcile import propose_reconciliation
from twinops.drift.table import render_drift_table
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


def _cmd_drift(args: argparse.Namespace) -> int:
    try:
        report = detect_drift(
            desired=args.desired,
            stage=args.stage,
            observed=args.observed,
            manifest=args.manifest,
        )
    except (DriftLoadError, ManifestError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_drift_table(report))

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        save_drift_report(report, out / "drift-report.json")
        write_html_report(report, out / "drift-report.html")
        print(f"\nWrote {out / 'drift-report.json'}")
        print(f"Wrote {out / 'drift-report.html'}")

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))

    if args.propose:
        proposal_dir = Path(args.propose)
        proposal = propose_reconciliation(report, proposal_dir)
        print(f"\nReconciliation proposal: {proposal.output_dir}")
        print(f"  overlay: {proposal.overlay_path}")
        print(f"  proposal: {proposal.proposal_path}")
        print(f"  pr draft: {proposal.summary_path}")

    return report.exit_code


def _cmd_reconcile(args: argparse.Namespace) -> int:
    try:
        report = detect_drift(
            desired=args.desired,
            stage=args.stage,
            observed=args.observed,
            manifest=args.manifest,
        )
    except (DriftLoadError, ManifestError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    proposal = propose_reconciliation(report, args.out)
    print(f"TwinOps reconciliation proposal for '{report.name}'")
    print(f"  changes: {len(proposal.changes)}")
    print(f"  overlay: {proposal.overlay_path}")
    print(f"  proposal: {proposal.proposal_path}")
    print(f"  pr draft: {proposal.summary_path}")
    if args.json:
        print(json.dumps(proposal.to_dict(), indent=2))
    return 0 if proposal.changes else 0


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

    drift = sub.add_parser(
        "drift",
        help="detect desired / rendered / observed drift",
    )
    drift.add_argument("--desired", required=True, help="desired state YAML")
    drift.add_argument("--stage", required=True, help="composed root.usda stage")
    drift.add_argument("--observed", required=True, help="observed telemetry JSON")
    drift.add_argument(
        "--manifest",
        default=None,
        help="optional DigitalTwin manifest for policy thresholds",
    )
    drift.add_argument(
        "--out",
        default=None,
        help="write drift-report.json and drift-report.html",
    )
    drift.add_argument(
        "--propose",
        default=None,
        help="also write a reconciliation proposal into this directory",
    )
    drift.add_argument("--json", action="store_true", help="print drift report JSON")
    drift.set_defaults(func=_cmd_drift)

    reconcile = sub.add_parser(
        "reconcile",
        help="generate a GitOps reconciliation proposal from drift",
    )
    reconcile.add_argument("--desired", required=True, help="desired state YAML")
    reconcile.add_argument("--stage", required=True, help="composed root.usda stage")
    reconcile.add_argument("--observed", required=True, help="observed telemetry JSON")
    reconcile.add_argument(
        "--manifest",
        default=None,
        help="optional DigitalTwin manifest for policy thresholds",
    )
    reconcile.add_argument(
        "--out",
        required=True,
        help="output directory for overlay and proposal files",
    )
    reconcile.add_argument("--json", action="store_true", help="print proposal JSON")
    reconcile.set_defaults(func=_cmd_reconcile)

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
