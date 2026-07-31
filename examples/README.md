# Examples

## assembly-line

Self-healing factory line demo used by almost every TwinOps path:

| Path | Command |
| --- | --- |
| Offline drift | `make demo` |
| Live UI | `make live-demo` |
| MQTT bridge | `make mqtt-smoke` |
| PLM change | `make plm-demo` |
| Operator | `make operator-demo` |

Key files:

- `twin.yaml` — DigitalTwin manifest
- `desired.yaml` — desired three-way state
- `telemetry.json` — static observed snapshot for offline drift
- `plm-catalog.json` — mock PLM system of record
- `mqtt-topics.json` — demo MQTT topic → prim bindings
- `assets/root.usda` — base OpenUSD stage

No GPU required for these demos.
