"""twinopsctl — CLI for the TwinOps Digital Twin Compiler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from twinops import __version__
from twinops.composer import compose_digital_twin
from twinops.doctor import run_doctor
from twinops.drift.apply import apply_proposal
from twinops.drift.csv_report import write_csv_report
from twinops.drift.engine import detect_drift, save_drift_report
from twinops.drift.html_report import write_html_report
from twinops.drift.loaders import DriftLoadError
from twinops.drift.reconcile import propose_reconciliation
from twinops.drift.sarif import write_sarif_report
from twinops.drift.table import render_drift_table
from twinops.plm.mock import load_adapter_for_example
from twinops.scene import assert_valid_scene_snapshot, build_scene_snapshot, write_scene_html
from twinops.schema import ManifestError, load_manifest


def _cmd_build(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output = Path(args.out) if args.out else Path("usd/generated") / manifest.name
    result = compose_digital_twin(manifest, output, copy_base_stage=not args.no_copy_base)

    if args.json:
        print(json.dumps(result.report, indent=2))
        return 0 if result.ok else 1

    print(f"TwinOps composed digital twin '{manifest.name}'")
    print(f"  output: {result.output_dir}")
    for key in ("root", "plm_overlay", "telemetry_overlay", "variant_overlay", "report"):
        path = result.files.get(key)
        if path:
            print(f"  {key}: {path}")

    for issue in result.issues:
        prefix = issue.severity.upper()
        print(f"  [{prefix}] {issue.code}: {issue.message}")

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

    if not args.json:
        print(render_drift_table(report))

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        save_drift_report(report, out / "drift-report.json")
        write_html_report(report, out / "drift-report.html")
        write_sarif_report(report, out / "drift-report.sarif")
        write_csv_report(report, out / "drift-report.csv")
        if not args.json:
            print(f"\nWrote {out / 'drift-report.json'}")
            print(f"Wrote {out / 'drift-report.html'}")
            print(f"Wrote {out / 'drift-report.sarif'}")
            print(f"Wrote {out / 'drift-report.csv'}")

    if args.sarif:
        path = write_sarif_report(report, args.sarif)
        if not args.json:
            print(f"Wrote {path}")

    if getattr(args, "csv", None):
        path = write_csv_report(report, args.csv)
        if not args.json:
            print(f"Wrote {path}")

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))

    if args.propose:
        proposal_dir = Path(args.propose)
        proposal = propose_reconciliation(report, proposal_dir)
        if not args.json:
            print(f"\nReconciliation proposal: {proposal.output_dir}")
            print(f"  overlay: {proposal.overlay_path}")
            print(f"  proposal: {proposal.proposal_path}")
            print(f"  pr draft: {proposal.summary_path}")

    return report.exit_code


def _cmd_scene(args: argparse.Namespace) -> int:
    """Build twinops.highlight.v1 from a drift report or by evaluating drift."""
    try:
        if getattr(args, "from_url", None):
            base = str(args.from_url).rstrip("/")
            status, body = _fetch_json(f"{base}/api/scene", timeout=getattr(args, "timeout", 3.0))
            if not body or status != 200:
                return 1
            scene = json.loads(body)
        elif args.from_report:
            payload = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
            twin_name = str((payload.get("metadata") or {}).get("name") or "twin")
            findings = list((payload.get("status") or {}).get("findings") or [])
            generated_at = (payload.get("metadata") or {}).get("generatedAt")
            scene = build_scene_snapshot(
                twin_name=twin_name,
                findings=findings,
                generated_at=generated_at,
            )
        else:
            if not args.desired or not args.stage or not args.observed:
                print(
                    "error: --desired/--stage/--observed required unless "
                    "--from-report/--from-url is set",
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
            scene = build_scene_snapshot(
                twin_name=twin_name,
                findings=findings,
                generated_at=generated_at,
            )
    except (DriftLoadError, ManifestError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if getattr(args, "strict", False):
        try:
            assert_valid_scene_snapshot(scene)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    lit = [prim for prim in scene["prims"] if prim["highlight"]["enabled"]]
    if args.json:
        # Machine-readable mode: JSON only on stdout (scripts/CI).
        print(json.dumps(scene, indent=2))
    else:
        print(f"Scene {scene['twin']} protocol={scene['protocol']['name']} lit={len(lit)}")
        for prim in lit:
            print(f"  HIGHLIGHT {prim['prim']} status={prim['status']}")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
        if not args.json:
            print(f"Wrote {out}")
    html_path = getattr(args, "html", None)
    if html_path:
        path = write_scene_html(scene, html_path)
        if not args.json:
            print(f"Wrote {path}")
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
    if args.json:
        print(json.dumps(proposal.to_dict(), indent=2))
        return 0
    print(f"TwinOps reconciliation proposal for '{report.name}'")
    print(f"  changes: {len(proposal.changes)}")
    print(f"  overlay: {proposal.overlay_path}")
    print(f"  proposal: {proposal.proposal_path}")
    print(f"  pr draft: {proposal.summary_path}")
    print("  next:    twinopsctl apply <proposal-dir>")
    return 0 if proposal.changes else 0


def _cmd_apply(args: argparse.Namespace) -> int:
    """Apply a local reconciliation proposal into a GitOps working tree."""
    try:
        result = apply_proposal(
            args.proposal_dir,
            repo=args.repo,
            target_dir=args.target_dir,
            branch=args.branch,
            commit=not args.no_commit,
        )
    except (OSError, RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    print(f"TwinOps applied proposal from {result.proposal_dir}")
    print(f"  branch:    {result.branch}")
    print(f"  target:    {result.target_dir}")
    print(f"  committed: {result.committed}")
    if result.commit_sha:
        print(f"  commit:    {result.commit_sha[:12]}")
    for path in result.files:
        print(f"  file:      {path}")
    return 0


def _cmd_plm_show(args: argparse.Namespace) -> int:
    try:
        adapter, catalog = load_adapter_for_example(args.example)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        payload = {
            "catalog": str(catalog),
            "items": [item.to_dict() for item in adapter.items],
        }
        print(json.dumps(payload, indent=2))
        return 0
    print(f"Mock PLM catalog: {catalog}")
    for item in adapter.items:
        label = f" ({item.name})" if item.name else ""
        print(
            f"  {item.item_id}{label}: rev={item.revision} "
            f"lifecycle={item.lifecycle} prim={item.prim}"
        )
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
    if args.json:
        print(json.dumps({"diffs": diffs, "hasDrift": bool(drifted)}, indent=2))
        return 1 if drifted else 0
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
    from twinops.api.auth import resolve_api_token

    example_dir = Path(args.example).resolve()
    work_dir = Path(args.work_dir).resolve() if args.work_dir else Path("usd/generated/live")
    web_dist = Path(args.web_dist).resolve() if args.web_dist else Path("web/dist")
    api_token = resolve_api_token(getattr(args, "api_token", None))
    app = create_app(
        example_dir=example_dir,
        work_dir=work_dir,
        interval_seconds=args.interval,
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        mqtt_ingest=not args.no_mqtt_ingest,
        autostart=True,
        web_dist=web_dist if web_dist.is_dir() else None,
        api_token=api_token,
    )
    base = f"http://{args.host}:{args.port}"
    print(f"TwinOps live API on {base}")
    print(f"  example: {example_dir}")
    print(f"  workdir: {work_dir}")
    print(f"  health:  {base}/api/health")
    print(f"  twin:    {base}/api/twin")
    print(f"  ready:   {base}/api/ready")
    print(f"  stream:  {base}/api/streaming/session")
    print(f"  ws:      ws://{args.host}:{args.port}/ws/events")
    print(f"  auth:    {'enabled' if api_token else 'disabled (demo)'}")
    if getattr(args, "open", False):
        import threading
        import webbrowser

        def _open() -> None:
            webbrowser.open(base)

        threading.Timer(0.8, _open).start()
        print(f"  browser: opening {base}")
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
    commands = (
        "build drift scene reconcile apply serve plm mqtt doctor health ready timeline "
        "proposal metrics live openapi version completion"
    )
    if args.shell == "bash":
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
    mqtt)
      if [[ ${{COMP_CWORD}} -eq 2 ]]; then
        COMPREPLY=( $(compgen -W "topics" -- "$cur") )
      fi
      ;;
    live)
      if [[ ${{COMP_CWORD}} -eq 2 ]]; then
        COMPREPLY=( $(compgen -W "status spike reconcile" -- "$cur") )
      fi
      ;;
    completion)
      COMPREPLY=( $(compgen -W "bash zsh" -- "$cur") )
      ;;
    *)
      COMPREPLY=( $(compgen -f -- "$cur") )
      ;;
  esac
}}
complete -F _twinopsctl_completions twinopsctl
"""
    elif args.shell == "zsh":
        script = f"""# twinopsctl zsh completion — eval "$(twinopsctl completion zsh)"
_twinopsctl_completions() {{
  local -a cmds sub
  cmds=({commands})
  if (( CURRENT == 2 )); then
    _describe -t commands 'twinopsctl command' cmds
    return
  fi
  case ${{words[2]}} in
    plm)
      sub=(show compare bump sync desired)
      _describe -t commands 'plm' sub
      ;;
    mqtt)
      sub=(topics)
      _describe -t commands 'mqtt' sub
      ;;
    live)
      sub=(status spike reconcile)
      _describe -t commands 'live' sub
      ;;
    completion)
      sub=(bash zsh)
      _describe -t commands 'shell' sub
      ;;
    *)
      _files
      ;;
  esac
}}
compdef _twinopsctl_completions twinopsctl
"""
    else:
        print(f"error: unsupported shell {args.shell!r} (bash|zsh)", file=sys.stderr)
        return 2
    print(script, end="")
    return 0


def _cmd_mqtt_topics(args: argparse.Namespace) -> int:
    from twinops.telemetry.topics import topic_catalog

    catalog = topic_catalog()
    if args.json:
        print(json.dumps(catalog, indent=2))
        return 0
    print(f"MQTT catalog: {catalog['metadata']['name']}")
    for binding in catalog["spec"]["bindings"]:
        print(f"  {binding['topic']} → {binding['prim']}#{binding['attribute']}")
    return 0


def _fetch_json(
    url: str,
    *,
    timeout: float,
    method: str = "GET",
    data: bytes | None = None,
) -> tuple[int, str]:
    import os
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    token = (os.environ.get("TWINOPS_API_TOKEN") or "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        print(f"error: HTTP {exc.code} from {url}", file=sys.stderr)
        return exc.code, ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"error: cannot reach {url}: {exc}", file=sys.stderr)
        return 0, ""


def _cmd_timeline(args: argparse.Namespace) -> int:
    """Fetch recent timeline events from a running live API."""
    base = args.base_url.rstrip("/")
    url = f"{base}/api/timeline?limit={args.limit}"
    status, body = _fetch_json(url, timeout=args.timeout)
    if not body:
        return 1

    if args.json:
        print(body)
        return 0 if status == 200 else 1
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print(body)
        return 0 if status == 200 else 1
    items = list(payload.get("items") or [])
    if not items:
        print("timeline: (empty)")
        return 0
    for item in items:
        ts = str(item.get("timestamp") or "")
        kind = str(item.get("type") or "?")
        summary = str(item.get("summary") or "")
        print(f"{ts}  {kind:<12}  {summary}")
    return 0 if status == 200 else 1


def _cmd_proposal(args: argparse.Namespace) -> int:
    """Fetch the latest reconciliation proposal from a running live API."""
    base = args.base_url.rstrip("/")
    url = f"{base}/api/proposal/latest"
    status, body = _fetch_json(url, timeout=args.timeout)
    if not body:
        return 1
    if args.json:
        print(body)
        return 0 if status == 200 else 1
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print(body)
        return 0 if status == 200 else 1
    if not payload:
        print("proposal: (none yet — run spike + reconcile first)")
        return 0
    meta = payload.get("metadata") or {}
    status_block = payload.get("status") or {}
    print(f"proposal: {meta.get('name') or 'latest'}")
    print(f"  applied: {status_block.get('applied')}")
    print(f"  changes: {status_block.get('changes')}")
    if status_block.get("overlayPath"):
        print(f"  overlay: {status_block.get('overlayPath')}")
    if status_block.get("summaryPath"):
        print(f"  summary: {status_block.get('summaryPath')}")
    return 0 if status == 200 else 1


def _cmd_metrics(args: argparse.Namespace) -> int:
    """Fetch live control-plane metrics JSON or Prometheus text."""
    base = args.base_url.rstrip("/")
    path = "/metrics" if args.prometheus else "/api/metrics"
    status, body = _fetch_json(f"{base}{path}", timeout=args.timeout)
    if not body:
        return 1
    if args.prometheus or args.json:
        print(body, end="" if body.endswith("\n") else "\n")
        return 0 if status == 200 else 1
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print(body)
        return 0 if status == 200 else 1
    print(f"twin:     {payload.get('twin')}")
    print(f"hasDrift: {payload.get('hasDrift')}")
    print(f"summary:  {payload.get('summary')}")
    print(f"highlights: {payload.get('highlightedPrims')}")
    print(f"mqttIngest: {payload.get('mqttIngestReceived')}")
    print(f"timeline: {payload.get('timelineEvents')}")
    return 0 if status == 200 else 1


def _cmd_live_status(args: argparse.Namespace) -> int:
    """Print a compact health/ready/metrics summary from a running live API."""
    base = args.base_url.rstrip("/")
    health_status, health_body = _fetch_json(f"{base}/api/health", timeout=args.timeout)
    ready_status, ready_body = _fetch_json(f"{base}/api/ready", timeout=args.timeout)
    metrics_status, metrics_body = _fetch_json(f"{base}/api/metrics", timeout=args.timeout)
    if not health_body or not ready_body or not metrics_body:
        return 1
    if args.json:
        payload = {
            "health": json.loads(health_body),
            "ready": json.loads(ready_body),
            "metrics": json.loads(metrics_body),
        }
        print(json.dumps(payload, indent=2))
        ok = (
            health_status == 200
            and ready_status == 200
            and metrics_status == 200
            and payload["ready"].get("status") == "ready"
        )
        return 0 if ok else 1
    health = json.loads(health_body)
    ready = json.loads(ready_body)
    metrics = json.loads(metrics_body)
    print(f"health:  {health.get('status')} version={health.get('version')}")
    print(
        f"ready:   {ready.get('status')} twin={ready.get('twin')} "
        f"hasDriftReport={ready.get('hasDriftReport')}"
    )
    print(
        f"metrics: hasDrift={metrics.get('hasDrift')} "
        f"highlights={metrics.get('highlightedPrims')} "
        f"timeline={metrics.get('timelineEvents')}"
    )
    return 0 if ready.get("status") == "ready" else 1


def _cmd_live_spike(args: argparse.Namespace) -> int:
    """POST /api/simulate/spike against a running live API."""
    base = args.base_url.rstrip("/")
    url = f"{base}/api/simulate/spike"
    status, body = _fetch_json(url, timeout=args.timeout, method="POST", data=b"{}")
    if not body:
        return 1
    if args.json:
        print(body)
        return 0 if status == 200 else 1
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print(body)
        return 0 if status == 200 else 1
    drift = (payload.get("drift") or {}).get("status") or {}
    print(f"spike: hasDrift={drift.get('hasDrift')} summary={drift.get('summary')}")
    return 0 if status == 200 else 1


def _cmd_live_reconcile(args: argparse.Namespace) -> int:
    """POST /api/reconcile against a running live API."""
    base = args.base_url.rstrip("/")
    url = f"{base}/api/reconcile"
    status, body = _fetch_json(url, timeout=args.timeout, method="POST", data=b"{}")
    if not body:
        return 1
    if args.json:
        print(body)
        return 0 if status == 200 else 1
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print(body)
        return 0 if status == 200 else 1
    drift = (payload.get("drift") or {}).get("status") or {}
    print(
        f"reconcile: changes={payload.get('changes')} "
        f"hasDrift={drift.get('hasDrift')} summary={drift.get('summary')}"
    )
    return 0 if status == 200 else 1


def _cmd_health(args: argparse.Namespace) -> int:
    """Probe a running live API `/api/health` endpoint."""
    base = args.base_url.rstrip("/")
    url = f"{base}/api/health"
    status, body = _fetch_json(url, timeout=args.timeout)
    if not body:
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


def _cmd_ready(args: argparse.Namespace) -> int:
    """Probe a running live API `/api/ready` endpoint."""
    base = args.base_url.rstrip("/")
    url = f"{base}/api/ready"
    status, body = _fetch_json(url, timeout=args.timeout)
    if not body:
        return 1
    if args.json:
        print(body)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return 0 if status == 200 else 1
        return 0 if status == 200 and payload.get("status") == "ready" else 1
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print(body)
        return 0 if status == 200 else 1
    print(f"status:         {payload.get('status')}")
    print(f"version:        {payload.get('version')}")
    print(f"twin:           {payload.get('twin')}")
    print(f"hasDriftReport: {payload.get('hasDriftReport')}")
    return 0 if status == 200 and payload.get("status") == "ready" else 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    checks = run_doctor(mqtt_host=args.mqtt_host, mqtt_port=args.mqtt_port)
    failed_required = [item for item in checks if item.required and not item.ok]
    if args.json:
        print(json.dumps({"checks": [item.to_dict() for item in checks]}, indent=2))
        if failed_required:
            print("doctor: required checks failed", file=sys.stderr)
            return 1
        return 0
    for item in checks:
        mark = "OK" if item.ok else ("MISSING" if item.required else "WARN")
        print(f"[{mark}] {item.name}: {item.detail}")
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
        help="write drift-report.json/.html/.sarif/.csv into this directory",
    )
    drift.add_argument(
        "--sarif",
        default=None,
        help="write SARIF 2.1.0 report to this path",
    )
    drift.add_argument(
        "--csv",
        default=None,
        help="write CSV findings report to this path",
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
    scene.add_argument(
        "--from-url",
        default=None,
        help="fetch live scene snapshot from BASE/api/scene",
    )
    scene.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout for --from-url")
    scene.add_argument("--out", default=None, help="write scene JSON to this path")
    scene.add_argument("--html", default=None, help="write offline scene HTML report")
    scene.add_argument(
        "--strict",
        action="store_true",
        help="validate snapshot against twinops.highlight.v1 shape",
    )
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

    apply_cmd = sub.add_parser(
        "apply",
        help="apply a reconciliation proposal into a local GitOps branch (no push)",
    )
    apply_cmd.add_argument("proposal_dir", help="directory with reconcile-overlay.usda")
    apply_cmd.add_argument(
        "--repo",
        default=".",
        help="git repository root (default: cwd)",
    )
    apply_cmd.add_argument(
        "--target-dir",
        default=None,
        help="where to copy artifacts (default: <repo>/usd/generated/applied)",
    )
    apply_cmd.add_argument(
        "--branch",
        default=None,
        help="branch override (default: proposal recommendedBranch)",
    )
    apply_cmd.add_argument(
        "--no-commit",
        action="store_true",
        help="copy artifacts only; do not git commit",
    )
    apply_cmd.add_argument("--json", action="store_true", help="print apply result JSON")
    apply_cmd.set_defaults(func=_cmd_apply)

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
    serve.add_argument(
        "--open",
        action="store_true",
        help="open the live UI in a browser after startup",
    )
    serve.add_argument(
        "--api-token",
        default=None,
        help="require bearer token (overrides TWINOPS_API_TOKEN when set)",
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

    mqtt = sub.add_parser("mqtt", help="MQTT demo helpers")
    mqtt_sub = mqtt.add_subparsers(dest="mqtt_command", required=True)
    mqtt_topics = mqtt_sub.add_parser("topics", help="print assembly-line MQTT topic catalog")
    mqtt_topics.add_argument("--json", action="store_true")
    mqtt_topics.set_defaults(func=_cmd_mqtt_topics)

    live = sub.add_parser("live", help="drive a running live API (spike / reconcile)")
    live_sub = live.add_subparsers(dest="live_command", required=True)
    live_status = live_sub.add_parser("status", help="compact health + ready + metrics")
    live_status.add_argument("--base-url", default="http://127.0.0.1:8080")
    live_status.add_argument("--timeout", type=float, default=3.0)
    live_status.add_argument("--json", action="store_true")
    live_status.set_defaults(func=_cmd_live_status)
    live_spike = live_sub.add_parser("spike", help="POST /api/simulate/spike")
    live_spike.add_argument("--base-url", default="http://127.0.0.1:8080")
    live_spike.add_argument("--timeout", type=float, default=10.0)
    live_spike.add_argument("--json", action="store_true")
    live_spike.set_defaults(func=_cmd_live_spike)
    live_reconcile = live_sub.add_parser("reconcile", help="POST /api/reconcile")
    live_reconcile.add_argument("--base-url", default="http://127.0.0.1:8080")
    live_reconcile.add_argument("--timeout", type=float, default=30.0)
    live_reconcile.add_argument("--json", action="store_true")
    live_reconcile.set_defaults(func=_cmd_live_reconcile)

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

    ready = sub.add_parser("ready", help="probe a running live API /api/ready")
    ready.add_argument("--base-url", default="http://127.0.0.1:8080")
    ready.add_argument("--timeout", type=float, default=3.0)
    ready.add_argument("--json", action="store_true")
    ready.set_defaults(func=_cmd_ready)

    timeline = sub.add_parser("timeline", help="fetch live API timeline events")
    timeline.add_argument("--base-url", default="http://127.0.0.1:8080")
    timeline.add_argument("--limit", type=int, default=20, help="max events to fetch")
    timeline.add_argument("--timeout", type=float, default=3.0)
    timeline.add_argument("--json", action="store_true")
    timeline.set_defaults(func=_cmd_timeline)

    proposal = sub.add_parser("proposal", help="fetch latest live API reconciliation proposal")
    proposal.add_argument("--base-url", default="http://127.0.0.1:8080")
    proposal.add_argument("--timeout", type=float, default=3.0)
    proposal.add_argument("--json", action="store_true")
    proposal.set_defaults(func=_cmd_proposal)

    metrics = sub.add_parser("metrics", help="fetch live API metrics JSON or Prometheus text")
    metrics.add_argument("--base-url", default="http://127.0.0.1:8080")
    metrics.add_argument("--timeout", type=float, default=3.0)
    metrics.add_argument("--json", action="store_true", help="print raw JSON body")
    metrics.add_argument(
        "--prometheus",
        action="store_true",
        help="fetch /metrics Prometheus exposition instead of /api/metrics",
    )
    metrics.set_defaults(func=_cmd_metrics)

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
        choices=["bash", "zsh"],
        help="shell type (bash or zsh)",
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
