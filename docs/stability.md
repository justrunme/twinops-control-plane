# Frozen contracts (TwinOps 1.0)

After **v1.0.0**, the following surfaces are a **stable baseline** for demos,
experimentation, and extension development.

They are **not** a guarantee of production industrial readiness.

## Stability rule

Incompatible changes require one of:

1. a migration note in [upgrade.md](upgrade.md), or
2. a new API / schema version (`apiVersion` / protocol name bump).

Additive, backward-compatible extensions are allowed without a major bump.

## Frozen surfaces

| Surface | Stability note |
|---------|----------------|
| `DigitalTwin` CRD | `twinops.io` group; additive CR fields preferred |
| Drift model | desired / rendered / observed + status vocabulary (`SYNCED`, `WARNING`, `DRIFT`, `CRITICAL`, `MISSING`) |
| Reconciliation proposal lifecycle | propose → apply (local Git artifacts) → verify |
| `TwinIncident` JSON | `apiVersion: twinops.io/v1alpha1`, `kind: TwinIncident` |
| PLM adapter interface | `PlmAdapter` protocol (`get` / `items` / `compare_manifest` / `sync_manifest` / `bump_revision`) |
| Highlight contract | `twinops.highlight.v1` scene snapshot |
| Live API JSON shapes | `/api/twin`, `/api/scene`, `/api/timeline`, `/api/drift/latest`, OpenAPI dump |
| OpenUSD attribute namespace | `twinops:*` custom attributes used by demos |

## Explicitly not frozen

- Streaming sidecar WebRTC answer format (`lab-echo` / `webrtc-software` / `webrtc-nvenc`)
- Mock / synthetic frame payloads
- Web UI layout and CSS
- Makefile helper targets (except documented entrypoints)
- Helm chart `version` (SemVer of chart ≠ TwinOps appVersion)
- Vendor PLM SDK stubs

## Extension guidance

Prefer:

- new adapters implementing `PlmAdapter` out-of-tree;
- new runtimes consuming `twinops.highlight.v1`;
- new exporters reading drift / incident JSON.

Avoid forking core schemas without a version bump.
