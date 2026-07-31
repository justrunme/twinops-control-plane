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
- Remaining: real Kit App Streaming session + browser client

## PLM adapter ✅ (mock)

- JSON catalog (`examples/assembly-line/plm-catalog.json`)
- `twinopsctl plm show|compare|bump|sync|desired`
- Vendor-neutral mock only — no proprietary PLM SDK

## Architecture decisions

- [ADR-0001](adr/0001-gitops-for-digital-twins.md) — GitOps for digital twins
- [ADR-0002](adr/0002-kubernetes-operator.md) — Kubernetes operator
- [ADR-0003](adr/0003-scene-highlight-protocol.md) — Scene highlight without GPU
- [ADR-0004](adr/0004-bidirectional-mqtt-bridge.md) — Bidirectional MQTT bridge
- [ADR-0005](adr/0005-drift-sarif-export.md) — Drift findings as SARIF
- [ADR-0006](adr/0006-mqtt-topic-catalog.md) — Shared MQTT topic catalog

## Non-goals (for now)

- Claiming production / enterprise readiness
- Hard-coding a specific commercial PLM product
- Requiring NVCF or cloud GPU to use the compiler
