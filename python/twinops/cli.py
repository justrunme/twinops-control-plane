"""twinopsctl — CLI for the TwinOps Digital Twin Compiler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from twinops import __version__
from twinops.composer import compose_digital_twin
from twinops.doctor import run_doctor
from twinops.drift.engine import detect_drift, save_drift_report
from twinops.drift.html_report import write_html_report
from twinops.drift.loaders import DriftLoadError
from twinops.drift.reconcile import propose_reconciliation
from twinops.drift.sarif import write_sarif_report
from twinops.drift.table import render_drift_table
from twinops.plm.mock import load_adapter_for_example
from twinops.scene import build_scene_snapshot, write_scene_html
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
        write_sarif_report(report, out / "drift-report.sarif")
        print(f"\nWrote {out / 'drift-report.json'}")
        print(f"Wrote {out / 'drift-report.html'}")
        print(f"Wrote {out / 'drift-report.sarif'}")

    if args.sarif:
        path = write_sarif_report(report, args.sarif)
        print(f"Wrote {path}")

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


def _cmd_scene(args: argparse.Namespace) -> int:
    """Build twinops.highlight.v1 from a drift report or by evaluating drift."""
    try:
        if args.from_report:
            payload = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
            twin_name = str((payload.get("metadata") or {}).get("name") or "twin")
            findings = list((payload.get("status") or {}).get("findings") or [])
            generated_at = (payload.get("metadata") or {}).get("generatedAt")
        else:
            if not args.desired or not args.stage or not args.observed:
                print(
                    "error: --desired/--stage/--observed required unless --from-report is set",
                    file=sys.stderr,
                )
                return 2
            report = detect_drift(
                desired=args.desired,
                stage=args.stage,
                observed=args.observed,
                manifest=args.manifest,
            )
            payload = report.to_dict()
            twin_name = report.name
            findings = list((payload.get("status") or {}).get("findings") or [])
            generated_at = report.generated_at
    except (DriftLoadError, ManifestError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    scene = build_scene_snapshot(
        twin_name=twin_name,
        findings=findings,
        generated_at=generated_at,
    )
    lit = [prim for prim in scene["prims"] if prim["highlight"]["enabled"]]
    print(f"Scene {scene['twin']} protocol={scene['protocol']['name']} lit={len(lit)}")
    for prim in lit:
        print(f"  HIGHLIGHT {prim['prim']} status={prim['status']}")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out}")
    html_path = getattr(args, "html", None)
    if html_path:
        path = write_scene_html(scene, html_path)
        print(f"Wrote {path}")
    if args.json:
        print(json.dumps(scene, indent=2))
    return 0 if not scene["hasDrift"] else 1


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


def _cmd_plm_show(args: argparse.Namespace) -> int:
    try:
        adapter, catalog = load_adapter_for_example(args.example)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Mock PLM catalog: {catalog}")
    for item in adapter.items:
        label = f" ({item.name})" if item.name else ""
        print(
            f"  {item.item_id}{label}: rev={item.revision} "
            f"lifecycle={item.lifecycle} prim={item.prim}"
        )
    if args.json:
        payload = {
            "catalog": str(catalog),
            "items": [item.to_dict() for item in adapter.items],
        }
        print(json.dumps(payload, indent=2))
    return 0


def _cmd_plm_compare(args: argparse.Namespace) -> int:
    try:
        adapter, catalog = load_adapter_for_example(args.example)
        manifest = load_manifest(Path(args.example) / "twin.yaml")
    except (OSError, ValueError, FileNotFoundError, ManifestError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    diffs = adapter.compare_manifest(manifest)
    drifted = [item for item in diffs if item["status"] != "SYNCED"]
    print(f"PLM compare catalog={catalog} manifest={manifest.source_path}")
    for item in diffs:
        status = item["status"]
        if status == "SYNCED":
            print(f"  [SYNCED] {item['itemId']} rev={item['revision']}")
        elif status == "DRIFT":
            print(
                f"  [DRIFT] {item['itemId']}: manifest={item['manifestRevision']} "
                f"catalog={item['catalogRevision']}"
            )
        else:
            print(f"  [{status}] {item['itemId']} catalog={item['catalogRevision']}")
    if args.json:
        print(json.dumps({"diffs": diffs, "hasDrift": bool(drifted)}, indent=2))
    return 1 if drifted else 0


def _cmd_plm_bump(args: argparse.Namespace) -> int:
    try:
        adapter, catalog = load_adapter_for_example(args.example)
        updated = adapter.bump_revision(args.item_id, to=args.revision)
        adapter.write_catalog(catalog)
    except (OSError, ValueError, FileNotFoundError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Bumped {updated.item_id} → revision {updated.revision}")
    print(f"  catalog: {catalog}")
    if args.sync_manifest:
        report = adapter.sync_manifest(Path(args.example) / "twin.yaml", write=True)
        print(f"  synced manifest changes: {len(report['changed'])}")
    if args.json:
        print(json.dumps(updated.to_dict(), indent=2))
    return 0


def _cmd_plm_sync(args: argparse.Namespace) -> int:
    try:
        adapter, catalog = load_adapter_for_example(args.example)
        report = adapter.sync_manifest(Path(args.example) / "twin.yaml", write=not args.dry_run)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    mode = "dry-run" if args.dry_run else "wrote"
    print(f"PLM sync ({mode}) catalog={catalog}")
    print(f"  items={report['items']} changed={len(report['changed'])}")
    for change in report["changed"]:
        print(f"  {change['itemId']}: {change['from']} → {change['to']}")
    if args.json:
        print(json.dumps(report, indent=2))
    return 0


def _cmd_plm_desired(args: argparse.Namespace) -> int:
    try:
        adapter, _catalog = load_adapter_for_example(args.example)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    fragment = adapter.desired_fragment()
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml_dump(fragment), encoding="utf-8")
        print(f"Wrote PLM desired fragment: {out}")
    else:
        print(yaml_dump(fragment), end="")
    return 0


def yaml_dump(data: object) -> str:
    import yaml

    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False)


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "error: live API deps missing. Install with: pip install -e '.[live]'",
            file=sys.stderr,
        )
        return 2

    from twinops.api.app import create_app

    example_dir = Path(args.example).resolve()
    work_dir = Path(args.work_dir).resolve() if args.work_dir else Path("usd/generated/live")
    web_dist = Path(args.web_dist).resolve() if args.web_dist else Path("web/dist")
    app = create_app(
        example_dir=example_dir,
        work_dir=work_dir,
        interval_seconds=args.interval,
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        mqtt_ingest=not args.no_mqtt_ingest,
        autostart=True,
        web_dist=web_dist if web_dist.is_dir() else None,
    )
    print(f"TwinOps live API on http://{args.host}:{args.port}")
    print(f"  example: {example_dir}")
    print(f"  workdir: {work_dir}")
    print(f"  health:  http://{args.host}:{args.port}/api/health")
    print(f"  twin:    http://{args.host}:{args.port}/api/twin")
    print(f"  ws:      ws://{args.host}:{args.port}/ws/events")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"twinopsctl {__version__}")
    return 0


def _cmd_openapi(args: argparse.Namespace) -> int:
    """Dump the live API OpenAPI schema without starting the server loop."""
    from twinops.api.app import create_app

    app = create_app(
        example_dir=args.example,
        work_dir=args.work_dir or "usd/generated/openapi-dump",
        interval_seconds=60,
        autostart=False,
    )
    schema = app.openapi()
    text = json.dumps(schema, indent=2)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {path}")
    else:
        print(text)
    return 0


def _cmd_completion(args: argparse.Namespace) -> int:
    """Print shell completion script for twinopsctl."""
    if args.shell != "bash":
        print(f"error: unsupported shell {args.shell!r} (only bash)", file=sys.stderr)
        return 2
    commands = (
        "build drift scene reconcile serve plm doctor health openapi version completion"
    )
    script = f"""# twinopsctl bash completion — eval "$(twinopsctl completion bash)"
_twinopsctl_completions() {{
  local cur prev
  COMPREPLY=()
  cur="${{COMP_WORDS[COMP_CWORD]}}"
  prev="${{COMP_WORDS[COMP_CWORD-1]}}"
  if [[ ${{COMP_CWORD}} -eq 1 ]]; then
    COMPREPLY=( $(compgen -W "{commands}" -- "$cur") )
    return 0
  fi
  case "${{COMP_WORDS[1]}}" in
    plm)
      if [[ ${{COMP_CWORD}} -eq 2 ]]; then
        COMPREPLY=( $(compgen -W "show compare bump sync desired" -- "$cur") )
      fi
      ;;
    completion)
      COMPREPLY=( $(compgen -W "bash" -- "$cur") )
      ;;
    *)
      COMPREPLY=( $(compgen -f -- "$cur") )
      ;;
  esac
}}
complete -F _twinopsctl_completions twinopsctl
"""
    print(script, end="")
    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    """Probe a running live API `/api/health` endpoint."""
    import urllib.error
    import urllib.request

    base = args.base_url.rstrip("/")
    url = f"{base}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=args.timeout) as resp:
            body = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as exc:
        print(f"error: HTTP {exc.code} from {url}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"error: cannot reach {url}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(body)
    else:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            print(body)
            return 0 if status == 200 else 1
        print(f"status:  {payload.get('status')}")
        print(f"version: {payload.get('version')}")
        print(f"service: {payload.get('service')}")
        mqtt = payload.get("mqtt") or {}
        if mqtt:
            print(f"mqtt:    {json.dumps(mqtt, sort_keys=True)}")
    return 0 if status == 200 else 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    checks = run_doctor(mqtt_host=args.mqtt_host, mqtt_port=args.mqtt_port)
    failed_required = [item for item in checks if item.required and not item.ok]
    for item in checks:
        mark = "OK" if item.ok else ("MISSING" if item.required else "WARN")
        print(f"[{mark}] {item.name}: {item.detail}")
    if args.json:
        print(json.dumps({"checks": [item.to_dict() for item in checks]}, indent=2))
    if failed_required:
        print("doctor: required checks failed", file=sys.stderr)
        return 1
    print("doctor: environment looks ready for local demos")
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
        help="write drift-report.json, .html, and .sarif into this directory",
    )
    drift.add_argument(
        "--sarif",
        default=None,
        help="write SARIF 2.1.0 report to this path",
    )
    drift.add_argument(
        "--propose",
        default=None,
        help="also write a reconciliation proposal into this directory",
    )
    drift.add_argument("--json", action="store_true", help="print drift report JSON")
    drift.set_defaults(func=_cmd_drift)

    scene = sub.add_parser(
        "scene",
        help="build twinops.highlight.v1 snapshot from drift (offline)",
    )
    scene.add_argument("--desired", default=None, help="desired state YAML")
    scene.add_argument("--stage", default=None, help="composed root.usda stage")
    scene.add_argument("--observed", default=None, help="observed telemetry JSON")
    scene.add_argument("--manifest", default=None, help="optional DigitalTwin manifest")
    scene.add_argument(
        "--from-report",
        default=None,
        help="build scene from an existing drift-report.json",
    )
    scene.add_argument("--out", default=None, help="write scene JSON to this path")
    scene.add_argument("--html", default=None, help="write offline scene HTML report")
    scene.add_argument("--json", action="store_true", help="print full scene JSON")
    scene.set_defaults(func=_cmd_scene)

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

    serve = sub.add_parser(
        "serve",
        help="run live telemetry simulator + drift API (HTTP/WebSocket)",
    )
    serve.add_argument(
        "--example",
        default="examples/assembly-line",
        help="example directory with twin.yaml / desired.yaml",
    )
    serve.add_argument(
        "--work-dir",
        default=None,
        help="workdir for composed stage (default: usd/generated/live)",
    )
    serve.add_argument("--host", default="127.0.0.1", help="bind host")
    serve.add_argument("--port", type=int, default=8080, help="bind port")
    serve.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="telemetry/drift tick interval seconds",
    )
    serve.add_argument(
        "--mqtt-host",
        default=None,
        help="optional MQTT broker host (in-process bus always enabled)",
    )
    serve.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    serve.add_argument(
        "--no-mqtt-ingest",
        action="store_true",
        help="publish to MQTT only; do not subscribe/ingest factory topics",
    )
    serve.add_argument(
        "--web-dist",
        default="web/dist",
        help="optional built web UI directory to serve at /",
    )
    serve.set_defaults(func=_cmd_serve)

    plm = sub.add_parser("plm", help="mock PLM adapter (catalog sync / compare / bump)")
    plm_sub = plm.add_subparsers(dest="plm_command", required=True)

    plm_show = plm_sub.add_parser("show", help="list mock PLM catalog items")
    plm_show.add_argument("--example", default="examples/assembly-line")
    plm_show.add_argument("--json", action="store_true")
    plm_show.set_defaults(func=_cmd_plm_show)

    plm_compare = plm_sub.add_parser("compare", help="compare catalog vs twin.yaml PLM mappings")
    plm_compare.add_argument("--example", default="examples/assembly-line")
    plm_compare.add_argument("--json", action="store_true")
    plm_compare.set_defaults(func=_cmd_plm_compare)

    plm_bump = plm_sub.add_parser("bump", help="bump an item revision in the catalog")
    plm_bump.add_argument("item_id", help="PLM item id, e.g. 1004711")
    plm_bump.add_argument("--example", default="examples/assembly-line")
    plm_bump.add_argument("--revision", default=None, help="explicit revision (default: A→B→C)")
    plm_bump.add_argument(
        "--sync-manifest",
        action="store_true",
        help="also write catalog revisions into twin.yaml",
    )
    plm_bump.add_argument("--json", action="store_true")
    plm_bump.set_defaults(func=_cmd_plm_bump)

    plm_sync = plm_sub.add_parser("sync", help="write catalog PLM mappings into twin.yaml")
    plm_sync.add_argument("--example", default="examples/assembly-line")
    plm_sync.add_argument("--dry-run", action="store_true")
    plm_sync.add_argument("--json", action="store_true")
    plm_sync.set_defaults(func=_cmd_plm_sync)

    plm_desired = plm_sub.add_parser("desired", help="emit PLM-only desired-state fragment")
    plm_desired.add_argument("--example", default="examples/assembly-line")
    plm_desired.add_argument("--out", default=None, help="optional output YAML path")
    plm_desired.set_defaults(func=_cmd_plm_desired)

    doctor = sub.add_parser("doctor", help="check local demo prerequisites")
    doctor.add_argument("--mqtt-host", default="127.0.0.1")
    doctor.add_argument("--mqtt-port", type=int, default=1883)
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=_cmd_doctor)

    health = sub.add_parser("health", help="probe a running live API /api/health")
    health.add_argument(
        "--base-url",
        default="http://127.0.0.1:8080",
        help="live API base URL",
    )
    health.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout seconds")
    health.add_argument("--json", action="store_true", help="print raw JSON body")
    health.set_defaults(func=_cmd_health)

    openapi = sub.add_parser("openapi", help="dump live API OpenAPI schema (no server)")
    openapi.add_argument("--example", default="examples/assembly-line")
    openapi.add_argument("--work-dir", default=None)
    openapi.add_argument("--out", default=None, help="write schema JSON to this path")
    openapi.set_defaults(func=_cmd_openapi)

    version = sub.add_parser("version", help="print version")
    version.set_defaults(func=_cmd_version)

    completion = sub.add_parser("completion", help="print shell completion script")
    completion.add_argument(
        "shell",
        nargs="?",
        default="bash",
        choices=["bash"],
        help="shell type (bash only for now)",
    )
    completion.set_defaults(func=_cmd_completion)

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
