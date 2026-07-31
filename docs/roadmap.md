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

## Milestone 3 — Kubernetes operator

- `DigitalTwin` CRD (Kubebuilder)
- Reconciliation: fetch → compose → store → status
- Conditions / finalizers
- Object storage upload
- envtest integration tests

## Milestone 4 — Live telemetry ✅ (API foundation)

- In-process MQTT-style simulator for assembly line
- Optional Mosquitto bridge (`deploy/demo/docker-compose.mqtt.yml`)
- Live drift evaluation loop
- HTTP + WebSocket control API (`twinopsctl serve`)
- Timeline event store for the web control plane

## Milestone 5 — Web control plane ✅ (foundation)

- React + Vite UI with live WebSocket updates
- Drift findings table
- Event timeline
- Heat-spike demo action
- Optional static hosting from `twinopsctl serve`

## Milestone 6 — Omniverse / GPU streaming

- Kit extension with scene highlighting
- GPU Operator notes / Helm values
- Kit App Streaming session lifecycle
- Browser streaming client

## Non-goals (for now)

- Claiming production / enterprise readiness
- Hard-coding a specific commercial PLM product
- Requiring NVCF or cloud GPU to use the compiler
