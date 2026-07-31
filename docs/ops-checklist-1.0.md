# TwinOps 1.0 — ops checklist (stable reference architecture)

**1.0 means stable reference architecture**, not a production industrial platform.

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
- [x] Real GPU → WebRTC MediaStream encoder — **deferred** (documented follow-up)

## Operations

- [x] API token auth + demo SSO JWT
- [x] HTTPS / mTLS lab path
- [x] Audit trail (SQLite audit_events)
- [x] Prometheus metrics (live + sidecar)
- [x] Documented backup/restore for SQLite state (`docs/backup-restore.md`)
- [x] Reproducible deploy (Helm umbrella + compose demos)
- [x] Upgrade notes (`docs/upgrade.md`)

## Quality

- [x] Tagged releases
- [x] Compatibility matrix (`docs/compatibility.md`)
- [x] E2E CI (`make e2e-demo` + sidecar smoke)
- [x] Security scanning (`make security-scan`; Actions on release / manual only)
- [x] No critical known failures in canonical E2E demo
- [x] Experimental limitations documented
- [x] Recorded walkthrough (owner)

## Deferred after 1.0

- NVENC / Kit App Streaming encoder into browser MediaStream
- Multi-session / multi-GPU streaming
- Proprietary PLM vendor SDKs
