# Upgrade notes

## 0.10.x → 0.11.x

- Command rename: `make portfolio-demo` → **`make e2e-demo`**
  (script: `scripts/e2e_demo.sh`, artifacts: `/tmp/twinops-e2e-demo`)
- New optional process: `twinopsctl streaming-sidecar`
- Live API mode `kit-sidecar` when `TWINOPS_STREAMING_SIDECAR_URL` is set
- No SQLite schema break from 0.10 → 0.11

## 0.11.x → 1.0.0

- Positioning: **stable reference architecture** (still not a production industrial platform)
- New docs: backup/restore, compatibility matrix, ops checklist
- CLI: `twinopsctl state backup|restore` for SQLite
- SQLite files from 0.10/0.11 remain readable (same schema)
- Streaming sidecar still uses mock frames by default; NVENC encoder remains a follow-up

## 1.0.x → 1.1.0

- Optional media extra: `pip install 'twinops[streaming]'` for real WebRTC tracks
- New sidecar flags/env: `--encoder`, `--kit-frame-dir`, `--input-mirror`,
  `TWINOPS_SIDECAR_ENCODER`, `TWINOPS_KIT_FRAME_DIR`, `TWINOPS_KIT_INPUT_MIRROR`
- New API: `POST /v1/sessions/{id}/input`; richer `/v1/status` + Prometheus stream gauges
- Default install without streaming extras still uses **lab-echo** (no break for CI)
- See [gpu-streaming.md](gpu-streaming.md)

## 1.1.x → 1.2.0

- **Breaking for Helm live**: Deployment `args` must be `serve ...` only (image ENTRYPOINT is `twinopsctl`)
- Prefer `spec.artifactSource` over hostPath `manifestPath` for DigitalTwin CRs
- Operator chart default `examples.enabled=false`; image tag **1.2.0**
- CI includes Helm/container deploy smoke and optional pxr validation
- See [release-1.2.md](release-1.2.md)

## 1.2.x → 1.3.0

- Durable output on DigitalTwin status (`status.output.uri` / digest / revision)
- In-cluster Helm operator E2E + namespaced RBAC mode
- Reconcile guards: build timeout, max concurrency, metrics, Events
- Prefer image/chart **1.3.1** over bare 1.3.0 (see below)
- See [release-1.3.md](release-1.3.md)

## 1.3.0 → 1.3.1

- **Breaking for output consumers**: ConfigMap switches from loose files to
  `binaryData.bundle.tar.gz` (includes `assets/`; extract before `Usd.Stage.Open`)
- Content digest is stable across rebuild/restart (volatile reports excluded)
- Workspace is always `/tmp/twinops/<ns>/<uid>`; `spec.outputDir` ignored for cleanup
- See [release-1.3.1.md](release-1.3.1.md), [ADR-0022](adr/0022-deterministic-output-bundle.md)

## Recommended upgrade path

```bash
git fetch --tags
git checkout v1.3.1
make install
make verify-all          # local; heavy — use before cutting releases
# or lighter:
make test && make e2e-demo && make streaming-sidecar-smoke && make deploy-smoke
make operator-incluster-e2e   # needs kind + docker
```

If you keep a persistent DB across upgrades:

```bash
twinopsctl state backup --db "$DB" --out /tmp/pre-1.0.sqlite
# upgrade package
twinopsctl state restore --db "$DB" --from /tmp/pre-1.0.sqlite
```

## Breaking / renamed surfaces

| Old | New |
|-----|-----|
| `make portfolio-demo` | `make e2e-demo` |
| `/tmp/twinops-portfolio-demo` | `/tmp/twinops-e2e-demo` |
| docs/portfolio-demo.md | docs/e2e-demo.md |
