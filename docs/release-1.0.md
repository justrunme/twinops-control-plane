# TwinOps v1.0 — release brief

**TwinOps v1.0 — Stable reference architecture for GitOps-managed industrial digital twins**

Stable API and architecture baseline for **demonstrations, experimentation, and
extension development**. Not production-ready industrial software.

## What is in scope

- OpenUSD digital-twin compiler (manifest → overlays / root stage)
- Three-way drift (desired / rendered / observed) + HTML/JSON/SARIF/CSV
- Reconciliation proposal + local Git apply + `--verify`
- Live control API + WebSocket timeline + web UI
- Bidirectional MQTT lab path (ACL/TLS demos)
- Kubernetes `DigitalTwin` operator + Helm umbrella
- File + REST PLM adapters (contract-tested); no vendor SDK in-tree
- TwinIncident export / replay with `--verify`
- SQLite persistence + `twinopsctl state backup|restore`
- Kit session-layer highlight runtime (source assets untouched)
- Single-session streaming sidecar (**mock frames** in CI)
- Auth: API token, HTTPS/mTLS lab, demo SSO JWT
- Prometheus metrics (live + sidecar)

## Consciously out of scope

- Production industrial platform claims
- Proprietary Teamcenter / Windchill SDKs
- Real RTX/NVENC → browser MediaStream encoder (planned follow-up: v1.1)
- Multi-session / multi-GPU / TURN / NVCF
- Policy engine / multi-twin fleet dashboard
- Remote GitHub App PR automation

## Upgrade from 0.11.x

See [upgrade.md](upgrade.md#011x--100). Summary:

- Same SQLite schema; use `state backup` before upgrade
- Positioning hardened to “stable reference architecture”
- No intentional breaking changes to frozen contracts ([stability.md](stability.md))

## Verified scenarios

Run on a clean clone:

```bash
make install
make test
make e2e-demo
make streaming-sidecar-smoke
make security-scan          # local / release-only Actions
```

Heavier gate:

```bash
make verify-all             # includes e2e-demo
```

| Scenario | Command / path |
|----------|----------------|
| Live spike → reconcile → SYNCED | `make live-demo-smoke` |
| Full operational lifecycle + artifacts | `make e2e-demo` |
| Offline GitOps apply/verify | `make demo-gitops` |
| Incident replay verify | `twinopsctl incident replay … --verify` |
| Streaming sidecar session lifecycle | `make streaming-sidecar-smoke` |
| SQLite backup/restore | `twinopsctl state backup|restore` |
| Persist across restart | covered inside `e2e-demo` |

## Known limitations

- Streaming sidecar defaults to **synthetic** frames; Kit `--frame-source kit` only supervises a process
- WebRTC answers are lab-echo until an encoder ships
- MQTT/TLS/mTLS/SSO paths are **lab demos**, not hardened IdP integrations
- Operator is a reference reconcile loop, not a multi-tenant SaaS controller
- Sample assembly-line twin is illustrative, not a factory digital thread

## Demo script

Recorded walkthrough checklist: [demo-script.md](demo-script.md)

One-command product story: [e2e-demo.md](e2e-demo.md)

Architecture: [architecture-one-pager.md](architecture-one-pager.md)
