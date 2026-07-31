# TwinOps 1.0 — ops checklist (stable reference architecture)

Use this after v0.11 sidecar lands. **1.0 means stable reference architecture**,
not a production industrial platform.

## Core

- [x] Deterministic OpenUSD composition
- [x] Three-way drift + verified reconciliation
- [x] Persisted incident history (SQLite)
- [x] Replay with `--verify`
- [x] Stable File/REST PLM adapter interface + contract tests
- [x] Kubernetes DigitalTwin operator
- [x] Stable live API contracts (OpenAPI dump)

## Omniverse

- [x] Kit extension session-layer highlighting
- [x] Reconnect / recovery / idempotent apply
- [x] Single-session streaming sidecar (mock path in CI)
- [ ] Real GPU → WebRTC MediaStream encoder (NVENC / Kit App Streaming) — follow-up

## Operations

- [x] API token auth + demo SSO JWT
- [x] HTTPS / mTLS lab path
- [x] Audit trail (SQLite audit_events)
- [x] Prometheus metrics (live + sidecar)
- [ ] Documented backup/restore for SQLite state
- [x] Reproducible deploy (Helm umbrella + compose demos)
- [ ] Upgrade notes for 0.10 → 0.11 → 1.0

## Quality

- [x] Tagged releases
- [ ] Compatibility matrix (Python / K8s / Kit versions)
- [x] E2E CI (`make e2e-demo` + sidecar smoke)
- [ ] Security scanning in CI
- [x] No critical known failures in canonical E2E demo
- [x] Experimental limitations documented

When the remaining boxes are closed (or explicitly deferred with docs), cut
`v1.0.0` as **stable reference architecture**.
