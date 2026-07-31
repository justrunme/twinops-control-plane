# Roadmap

TwinOps is a **GitOps / Kubernetes control plane for industrial digital twins**.
Omniverse Kit is an optional OpenUSD runtime — not the product center.

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

- Desired / rendered / observed model
- Policy thresholds (warning / critical)
- ASCII table + JSON + HTML dashboard
- Reconciliation proposal (USD overlay + PR draft)
- Self-healing demo script (`make demo`)

## Milestone 3 — Kubernetes operator ✅ (foundation)

- `DigitalTwin` CRD + Go types
- controller-runtime reconcile loop
- Helm chart + sample CR

## Milestone 4 — Live telemetry ✅ (API foundation)

- MQTT-style simulator + optional Mosquitto
- Bidirectional MQTT ingest
- HTTP + WebSocket control API

## Milestone 5 — Web control plane ✅ (foundation)

- React + Vite UI with live WebSocket updates
- One-command live demo (`make live-demo`)

## Milestone 6 — Runtime contracts ✅ (foundation)

- `twinops.highlight.v1` + web scene inspector
- Lab WebRTC signaling + browser MediaStream
- HTTPS / mTLS / demo SSO JWT
- Local GitOps apply `--verify`

## v0.7 — Omniverse Kit scene runtime 🚧

- [x] Pluggable highlight appliers (`plan` / `overlay` / `kit`)
- [x] `TwinOpsSceneRuntime` poll/WS loop
- [x] Kit extension starts runtime + applies displayColor/selection
- [ ] Kit App Streaming sidecar (GPU frames → browser) — follows lab WebRTC

## v0.8 — Incident history / timeline / replay ⏳

- Persist twin timeline as incident records
- `record.json` export of spike → proposal → apply → recover
- Replay engine to re-run an incident against the twin
- Richer timeline visualization in the web UI

## v0.9 — Generic PLM adapters ⏳

- File adapter (JSON catalog — today's mock shape)
- Generic REST adapter (`GET /items/{id}` → id/revision/lifecycle/metadata)
- Adapter SDK docs so others can add Teamcenter/Windchill later
- **No** proprietary PLM SDK in-tree

## v1.0 — Reference demo complete ⏳

When all of the following exist:

- Kit scene runtime + optional streaming sidecar
- Incident replay + history
- Generic PLM adapters
- Recorded 5–7 minute walkthrough (owner)

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
- [ADR-0012](adr/0012-kit-streaming-mock-contract.md) — Kit streaming mock contract
- [ADR-0013](adr/0013-live-mtls-and-sso.md) — Live API mTLS and demo SSO JWT
- [ADR-0014](adr/0014-lab-webrtc-streaming.md) — Lab WebRTC streaming path
- [ADR-0015](adr/0015-kit-scene-runtime.md) — Kit scene runtime backends

## Non-goals (for now)

- Claiming production / enterprise readiness
- Hard-coding a specific commercial PLM product / proprietary SDK
- Requiring NVCF or cloud GPU to use the compiler
- Remote GitHub App PR automation (local `--print-pr` is enough)
- Exploding CLI surface / micro-releases around the product
