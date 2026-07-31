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

## Milestone 4 — Live telemetry

- MQTT simulator for assembly line
- Telemetry adapter
- Transient / session layer updates
- Drift events to Prometheus

## Milestone 5 — Omniverse Kit extension

- `twinops.dashboard` extension
- Prim walk + metadata panel
- Drift color highlighting
- Reconcile request action

## Milestone 6 — GPU streaming

- NVIDIA GPU Operator notes / Helm values
- Containerized Kit App
- Application / Profile CRs (Kit App Streaming)
- Browser client + idle timeout
- DCGM / Grafana dashboard

## Non-goals (for now)

- Claiming production / enterprise readiness
- Hard-coding a specific commercial PLM product
- Requiring NVCF or cloud GPU to use the compiler
