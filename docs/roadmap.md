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

## v0.8 — Incident history / timeline / replay ✅

- TwinIncident JSON model + export from timeline
- Replay engine re-runs drift per incident step
- Sample `incident-heat-spike.json` fixture
- Richer web timeline visualization — follow-up polish

## v0.9 — Generic PLM adapters ✅

- FilePlmAdapter (JSON catalog)
- RestPlmAdapter (`GET /items`, `GET /items/{id}`, optional PUT)
- Adapter SDK docs (`docs/plm-adapters.md`)
- **No** proprietary PLM SDK in-tree

## v0.10 — Productization (E2E operational twin) ✅

- `make e2e-demo` one-command lifecycle + CI artifacts
- SQLite persistence (timeline / proposals / audit)
- Verified incident replay
- PLM adapter contract tests
- Kit session-layer highlight loop (source assets untouched)

## v0.11 — Kit Streaming sidecar ✅

- Single-session streaming sidecar (mock frames in CI; Kit supervisor optional)
- Health / readiness / idle timeout / graceful shutdown / GPU metrics
- Live API mode \`kit-sidecar\` via sidecar URL
- Honest limitations: no NVENC/TURN/NVCF yet

## v1.0 — Stable reference architecture ✅

See [ops-checklist-1.0.md](ops-checklist-1.0.md), [release-1.0.md](release-1.0.md),
and [stability.md](stability.md) (frozen contracts).

Core feature work is **frozen**. Next code epic only:

## v1.1 — Real Kit GPU streaming path ✅

Single GPU · single Kit session · software/NVENC host path → WebRTC MediaStream
(or lab-echo fallback). Not multi-user, not NVCF, not autoscaling.
See [ADR-0020](adr/0020-kit-gpu-encoder-path.md), [gpu-streaming.md](gpu-streaming.md).

## v1.2 — Production hardening ✅

Helm/container deploy path fixed and CI-tested; DigitalTwin artifactSource;
software WebRTC test + host NVENC **ingest** bridge (aiortc still encodes WebRTC);
optional pxr validation. See [release-1.2.md](release-1.2.md).

## v1.2.1 — Correctness patch ✅

Media honesty fields/tests; atomic artifacts + ConfigMap watch + kind E2E;
Helm sample `outputDir` under `/tmp/twinops`; finalizer workspace cleanup;
artifact size/DNS fail-closed. See [release-1.2.1.md](release-1.2.1.md).

## v1.3 — Single-twin pilot ready ✅

- [x] Persistent output artifact URI + digest (ConfigMap publish; OCI later) — ADR-0021
- [x] Reconcile timeout / concurrency / build idempotency
- [x] Operator metrics + Kubernetes Events
- [x] In-cluster Helm operator E2E + restart recovery
- [x] Namespace-scoped RBAC mode
- [x] Supply-chain scans (govulncheck, pip-audit, Trivy, SBOM)

See [release-1.3.md](release-1.3.md).

## v1.3.1 — Pilot correctness ✅

- [x] Deterministic full USD bundle (`bundle.tar.gz` + `assets/`) — ADR-0022
- [x] pxr Stage.Open of extracted output in E2E
- [x] Stable output digest/revision after restart
- [x] Controller-owned workspace cleanup only
- [x] Helm `artifactRequireURLDigest` + securityContext
- [x] Trivy streaming-sidecar

See [release-1.3.1.md](release-1.3.1.md).

## v1.4 — Immutable outputs + isolated Jobs ✅

- [x] Immutable ConfigMap / OCI / S3 output revisions — ADR-0024
- [x] `spec.build.mode=job` sandboxed Kubernetes Job — ADR-0023
- [x] status.output.history + keepRevisions GC
- [x] Helm build SA + Job RBAC

See [release-1.4.md](release-1.4.md).

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
- [ADR-0016](adr/0016-incident-replay.md) — Twin incident history and replay
- [ADR-0017](adr/0017-generic-plm-adapters.md) — Generic File and REST PLM adapters
- [ADR-0018](adr/0018-productization-e2e.md) — Productization end-to-end scenario
- [ADR-0019](adr/0019-kit-streaming-sidecar.md) — Single-session Kit streaming sidecar
- [ADR-0020](adr/0020-kit-gpu-encoder-path.md) — Real Kit GPU encoder path (v1.1)

## Non-goals (for now)

- Claiming production / enterprise readiness
- Hard-coding a specific commercial PLM product / proprietary SDK
- Requiring NVCF or cloud GPU to use the compiler
- Remote GitHub App PR automation (local `--print-pr` is enough)
- Exploding CLI surface / micro-releases around the product
