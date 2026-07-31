# TwinOps documentation

Navigation index for the control plane docs.

## Start here

| Goal | Doc |
| --- | --- |
| Architecture overview | [architecture.md](architecture.md) |
| 2-minute live demo | [demo.md](demo.md) |
| 5–7 minute demo script | [demo-script.md](demo-script.md) |
| Sequence diagrams | [sequences.md](sequences.md) |
| Local prerequisites | `make doctor` / [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Cutting a release | [RELEASING.md](../RELEASING.md) |

## Subsystems

| Topic | Doc |
| --- | --- |
| OpenUSD model | [openusd-model.md](openusd-model.md) |
| Live telemetry + MQTT | [live-telemetry.md](live-telemetry.md) |
| Kubernetes operator | [operator.md](operator.md) |
| Container images (GHCR) | [images.md](images.md) |
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
| [0007](adr/0007-local-gitops-apply.md) | Local GitOps apply |
| [0008](adr/0008-live-api-token-auth.md) | Optional live API token |
| [0009](adr/0009-mqtt-payload-schema.md) | MQTT payload schema |
| [0010](adr/0010-apply-verify-loop.md) | Apply verification loop |
| [0011](adr/0011-lab-mqtt-tls.md) | Lab MQTT TLS stub |
| [0012](adr/0012-kit-streaming-mock-contract.md) | Kit streaming mock contract |
| [0013](adr/0013-live-mtls-and-sso.md) | Live API mTLS and demo SSO JWT |
| [0014](adr/0014-lab-webrtc-streaming.md) | Lab WebRTC streaming path |

## Schemas

| Schema | Path |
| --- | --- |
| Scene highlight | [`schemas/twinops.highlight.v1.json`](../schemas/twinops.highlight.v1.json) |
| MQTT payload | [`schemas/twinops.mqtt.payload.v1.json`](../schemas/twinops.mqtt.payload.v1.json) |

## Examples

See [examples/README.md](../examples/README.md).
