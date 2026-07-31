# Architecture

## Goal

Treat an industrial digital twin like infrastructure:

```text
declare desired twin state in Git
        →
compose OpenUSD layers
        →
reconcile against rendered stage and observed telemetry
        →
optionally serve an Omniverse runtime session
```

## Current scope (Milestone 0–6 foundation)

Live path:

```text
simulator / MQTT ingest
      → observed state
      → drift loop
      → /api/scene highlight + WebSocket
      → web UI / Kit stub
```

Compiler + drift path (Milestone 0–2):

```text
DigitalTwin YAML
      │
      ▼
┌─────────────────────┐
│ twinopsctl build    │
│ (Python compiler)   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐     ┌──────────────────────┐
│ composed stage      │────▶│ twinopsctl drift     │
│ root + overlays     │     │ desired/rendered/obs │
└─────────────────────┘     └──────────┬───────────┘
                                       │
                          ┌────────────┼────────────┐
                          ▼            ▼            ▼
                     table/JSON   HTML report   reconcile
                                                overlay+PR
```

No Kubernetes, GPU, or Omniverse runtime is required for this path.

## Target architecture

```text
                         ┌─────────────────────┐
                         │ Git repository       │
                         │ DigitalTwin CRs      │
                         │ USD layer manifests  │
                         └──────────┬──────────┘
                                    │
                                    ▼
┌─────────────┐          ┌─────────────────────┐
│ PLM adapter │─────────▶│ TwinOps Controller   │
│ mock        │          │ Kubernetes operator  │
└─────────────┘          └──────────┬──────────┘
                                    │
┌─────────────┐                     ├─────────────┐
│ MQTT / IoT  │────────────────────▶│             │
└─────────────┘                     ▼             ▼
                           ┌────────────────┐  ┌───────────────┐
                           │ USD Composer   │  │ Session       │
                           │ layer generator│  │ Orchestrator  │
                           └───────┬────────┘  └───────┬───────┘
                                   │                   │
                                   ▼                   ▼
                           ┌────────────────┐  ┌───────────────┐
                           │ Object storage │  │ Kit App       │
                           │ S3 / MinIO     │  │ Streaming     │
                           └───────┬────────┘  └───────┬───────┘
                                   │                   │
                                   └──────────┬────────┘
                                              ▼
                                       Browser client
```

## Control-plane components (planned)

| Component            | Role                                              |
| -------------------- | ------------------------------------------------- |
| DigitalTwin CRD      | Desired twin declaration                          |
| TwinAsset CRD        | Versioned USD asset reference                     |
| TwinOps Controller   | Reconciliation loop                               |
| USD Composer         | Layer generation / stage assembly                 |
| Drift Engine         | Compare desired / rendered / observed             |
| PLM Adapter          | Generic mock first; vendor adapters later         |
| Telemetry Adapter    | MQTT / simulator                                  |
| Session Orchestrator | Kit App Streaming session lifecycle               |
| Web UI               | Control panel, drift timeline, streaming embed    |

## OpenUSD composition model

TwinOps uses non-destructive composition:

1. **Base stage** — geometry and structure (`assets/root.usda`)
2. **PLM overlay** — item IDs, revisions, lifecycle metadata
3. **Telemetry overlay** — live attribute bindings / defaults
4. **Variant overlay** — operational mode selection
5. **Root stage** — sublayers the above into one renderable composition

Custom attributes use the `twinops:` namespace, for example:

- `twinops:plmItemId`
- `twinops:plmRevision`
- `twinops:temperature`
- `twinops:status`
- `twinops:firmware`

See [openusd-model.md](openusd-model.md).

## Drift model (Milestone 2)

```text
desired  ≠ rendered  ≠ observed
```

| Status   | Meaning                                      |
| -------- | -------------------------------------------- |
| SYNCED   | All three views agree within policy          |
| DRIFT    | Desired/rendered/observed disagree           |
| MISSING  | Expected signal or prim is unavailable       |
| WARNING  | Policy threshold exceeded (e.g. temperature) |

## Honesty boundaries

- Omniverse Kit / streaming are **optional** runtimes, not assumed.
- Object storage starts as local filesystem / S3-compatible paths.
- PLM is a mock adapter until a deliberate integration exists.
- GPU Operator and Kit App Streaming arrive only in later milestones.
