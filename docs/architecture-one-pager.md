# TwinOps architecture (one-pager)

TwinOps is a **GitOps / Kubernetes control plane** for industrial digital twins.
Omniverse Kit is an **optional runtime**, not the center of the product.

## Control loop

```text
Desired: Git / PLM
Rendered: OpenUSD
Observed: MQTT / IoT
          ↓
       Drift
          ↓
 Proposal → Git apply → rebuild → verify
          ↓
       SYNCED
```

## Boundaries

```text
Core TwinOps
├── compiler (manifest → OpenUSD overlays)
├── drift / reconciliation
├── Kubernetes operator (DigitalTwin CR)
├── incidents / replay
├── PLM adapters (File + REST protocol)
└── API / security (token, mTLS, demo SSO)

Optional runtimes
├── Web UI
├── Omniverse Kit (session-layer highlights)
└── WebRTC / streaming sidecar (mock / kit-file / NVENC host in 1.1)
```

## Three-way state

| Plane | Source | Role |
|-------|--------|------|
| Desired | Git + PLM mappings | Authoritative engineering intent |
| Rendered | Composed OpenUSD stage | What the twin scene currently encodes |
| Observed | MQTT / simulator / IoT | Live factory signal |

Drift is the difference across those planes. Reconciliation produces a Git-backed
proposal (USD overlay + PR draft), optional local apply, and verify → SYNCED.

## Stable contracts (1.0)

See [stability.md](stability.md). Breaking changes require a migration note or a
new API version.

## Related

- [architecture.md](architecture.md) — longer overview
- [e2e-demo.md](e2e-demo.md) — one-command operational scenario
- [streaming-sidecar.md](streaming-sidecar.md) — optional Kit streaming path
- [gpu-streaming.md](gpu-streaming.md) — GPU/driver compatibility for v1.1
- [ops-checklist-1.0.md](ops-checklist-1.0.md) — 1.0 definition of done
