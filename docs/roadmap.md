# Roadmap

## Milestone 0 — Repository foundation ✅

- README, license, architecture docs
- ADR-0001: GitOps for digital twins
- Sample DigitalTwin manifest
- Sample OpenUSD assembly-line stage

## Milestone 1 — OpenUSD Digital Twin Compiler ✅

- YAML schema loader
- Python composer generating USDA overlays
- Variant selection
- PLM / telemetry metadata injection
- Validation + reconciliation report
- Unit tests + GitHub Actions CI

## Milestone 2 — Drift engine ✅

```bash
twinopsctl drift \
  --desired examples/assembly-line/desired.yaml \
  --stage examples/assembly-line/generated/root.usda \
  --observed examples/assembly-line/telemetry.json \
  --manifest examples/assembly-line/twin.yaml \
  --out examples/assembly-line/generated/drift \
  --propose examples/assembly-line/generated/proposal
```

- Desired / rendered / observed model
- Policy thresholds (warning / critical)
- ASCII table + JSON + HTML dashboard
- Reconciliation proposal (USD overlay + PR draft)
- Self-healing demo script (`make demo`)
- Tests

## Milestone 3 — Kubernetes operator ✅ (foundation)

- `DigitalTwin` CRD + Go types
- controller-runtime reconcile loop (`build` + optional `drift`)
- Status phases / conditions / finalizer
- Helm chart + sample CR
- Local `make operator-run`

## Milestone 4 — Live telemetry ✅ (API foundation)

- In-process MQTT-style simulator for assembly line
- Optional Mosquitto bridge (`deploy/demo/docker-compose.mqtt.yml`)
- Bidirectional MQTT: publish + ingest (external PLC → observed state)
- Live drift evaluation loop
- HTTP + WebSocket control API (`twinopsctl serve`)
- Timeline event store for the web control plane

## Milestone 5 — Web control plane ✅ (foundation)

- React + Vite UI with live WebSocket updates
- Drift findings table
- Event timeline
- Heat-spike + reconcile demo actions
- Optional static hosting from `twinopsctl serve`
- One-command live demo (`make live-demo`)

## Milestone 6 — Omniverse / GPU streaming ✅ (foundation)

- `GET /api/scene` highlight contract (`twinops.highlight.v1`)
- Web scene inspector (drift-colored prim tree, no GPU)
- Kit extension stub that polls TwinOps without Omniverse installed
- GPU Operator / Kit App Streaming notes (`docs/omniverse.md`)
- Mock Kit streaming viewport in web UI (GPU placeholder)
- `GET /api/streaming/session` mock session descriptor
- Remaining: real Kit App Streaming session + browser WebRTC client

## Milestone 7 — GitOps apply loop ✅ (foundation)

- `twinopsctl apply` local branch + artifact copy (no remote push)
- Apply receipt + ADR-0007
- Remaining: GitHub App / remote PR automation

## Milestone 8 — Live API auth + operator sync ✅ (foundation)

- Optional bearer token (`TWINOPS_API_TOKEN` / `--api-token`) — ADR-0008
- Operator `spec.liveAPIURL` → `status.live` probe
- Helm live Deployment mounts `TWINOPS_API_TOKEN` from Secret (umbrella)
- Operator `spec.liveAPITokenSecretRef` resolves bearer token from Secret
- Remaining: mTLS

## Milestone 9 — Industrial contour ✅ (stubs)

- `PlmAdapter` protocol (mock implements it)
- Teamcenter/Windchill stub adapters (NotImplemented mutations)
- MQTT payload schema `schemas/twinops.mqtt.payload.v1.json` + optional strict ingest
- Grafana dashboard stub (`deploy/observability/grafana/`)
- Helm umbrella notes + optional `sampleTwin.liveAPIURL`
- Mosquitto ACL demo profile + Helm umbrella skeleton (0.5.x)
- Lab MQTT TLS compose stub (`:8883`, self-signed) + Secret-backed live token
- Umbrella `Chart.lock` + `make helm-deps` / `make helm-template`
- Remaining: production-grade MQTT (CA, client certs), published GHCR images

## Milestone 10 — Demo credibility ✅ (docs)

- [Demo script](demo-script.md) for 5–7 minute walkthrough
- Portfolio sync for public narrative

## PLM adapter ✅ (mock)

- JSON catalog (`examples/assembly-line/plm-catalog.json`)
- `twinopsctl plm show|compare|bump|sync|desired`
- Vendor-neutral mock only — no proprietary PLM SDK
- `PlmAdapter` protocol for future vendor stubs

## Architecture decisions

- [ADR-0001](adr/0001-gitops-for-digital-twins.md) — GitOps for digital twins
- [ADR-0002](adr/0002-kubernetes-operator.md) — Kubernetes operator
- [ADR-0003](adr/0003-scene-highlight-protocol.md) — Scene highlight without GPU
- [ADR-0004](adr/0004-bidirectional-mqtt-bridge.md) — Bidirectional MQTT bridge
- [ADR-0005](adr/0005-drift-sarif-export.md) — Drift findings as SARIF
- [ADR-0006](adr/0006-mqtt-topic-catalog.md) — Shared MQTT topic catalog
- [ADR-0007](adr/0007-local-gitops-apply.md) — Local GitOps apply
- [ADR-0008](adr/0008-live-api-token-auth.md) — Optional live API token
- [ADR-0009](adr/0009-mqtt-payload-schema.md) — MQTT payload schema
- [ADR-0010](adr/0010-apply-verify-loop.md) — Apply verification loop
- [ADR-0011](adr/0011-lab-mqtt-tls.md) — Lab MQTT TLS stub

## Next focus (0.5.x → 0.6)

Done in 0.5.x: GHCR publish workflow, apply `--verify`, MQTT ACL, Kit `--ws`, Helm umbrella + live stub,
lab MQTT TLS compose + serve TLS client flags, Secret-mounted live API token, `liveAPITokenSecretRef`,
`Chart.lock` / `make helm-deps`, `make demo-gitops`.

1. Real Kit App Streaming session + browser WebRTC (still mock today)
2. GHCR images publishing on each `v*` tag (verified pull for 0.5.6+)
3. Recorded 5–7 minute demo using `docs/demo-script.md` / `make demo-gitops`
4. Live API mTLS / SSO (token + SecretRef remain the demo auth path)

## Non-goals (for now)

- Claiming production / enterprise readiness
- Hard-coding a specific commercial PLM product
- Requiring NVCF or cloud GPU to use the compiler
- Remote GitHub App PR automation (local `--print-pr` is enough for now)
