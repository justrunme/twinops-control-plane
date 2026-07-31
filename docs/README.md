# TwinOps documentation

Navigation index for the control plane docs.

## Start here

| Goal | Doc |
| --- | --- |
| Architecture overview | [architecture.md](architecture.md) |
| 2-minute live demo | [demo.md](demo.md) |
| Local prerequisites | `make doctor` / [CONTRIBUTING.md](../CONTRIBUTING.md) |

## Subsystems

| Topic | Doc |
| --- | --- |
| OpenUSD model | [openusd-model.md](openusd-model.md) |
| Live telemetry + MQTT | [live-telemetry.md](live-telemetry.md) |
| Kubernetes operator | [operator.md](operator.md) |
| Omniverse / scene highlights | [omniverse.md](omniverse.md) |
| Mock PLM adapter | [plm-adapter.md](plm-adapter.md) |
| Security notes | [security.md](security.md) |
| Roadmap | [roadmap.md](roadmap.md) |

## Architecture decisions

| ADR | Title |
| --- | --- |
| [0001](adr/0001-gitops-for-digital-twins.md) | GitOps for digital twins |
| [0002](adr/0002-kubernetes-operator.md) | Kubernetes operator |
| [0003](adr/0003-scene-highlight-protocol.md) | Scene highlight without GPU |
| [0004](adr/0004-bidirectional-mqtt-bridge.md) | Bidirectional MQTT bridge |
| [0005](adr/0005-drift-sarif-export.md) | Drift findings as SARIF |
| [0006](adr/0006-mqtt-topic-catalog.md) | Shared MQTT topic catalog |

## Schemas

| Schema | Path |
| --- | --- |
| Scene highlight | [`schemas/twinops.highlight.v1.json`](../schemas/twinops.highlight.v1.json) |

## Examples

See [examples/README.md](../examples/README.md).
