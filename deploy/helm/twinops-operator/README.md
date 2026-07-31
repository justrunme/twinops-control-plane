# twinops-operator Helm chart

Installs the TwinOps Kubernetes operator that reconciles `DigitalTwin` CRs.

## Prerequisites

- Kubernetes 1.27+ (k3d/kind work for demos)
- `twinopsctl` available in the manager image / hostPath for demos
- CRDs bundled under `crds/`

## Install

```bash
helm upgrade --install twinops-operator deploy/helm/twinops-operator \
  --namespace twinops-system \
  --create-namespace
```

Apply a sample CR after install (see `docs/operator.md` and `make operator-demo`).

## Values

| Key | Default | Notes |
| --- | --- | --- |
| `image.repository` | `ghcr.io/justrunme/twinops-operator` | Build via `Dockerfile.operator` |
| `image.tag` | `0.1.0` | Keep in sync with Chart `appVersion` |
| `twinopsctlPath` | `/usr/local/bin/twinopsctl` | Path inside the manager container |
| `examples.enabled` | `true` | HostPath mount for local demos |
| `liveMetrics.enabled` | `false` | Scrape notes for co-located live API |
| `sampleTwin.enabled` | `false` | Optionally install a demo DigitalTwin CR |
| `sampleTwin.liveAPIURL` | `""` | Populate `status.live` via live API probe |
| `sampleTwin.liveAPITokenSecretRef` | `name: ""` | Prefer Secret over plaintext `liveAPIToken` |

Enable a sample twin that also probes a live API:

```bash
helm upgrade --install twinops-operator deploy/helm/twinops-operator \
  --namespace twinops-system --create-namespace \
  --set sampleTwin.enabled=true \
  --set sampleTwin.liveAPIURL=http://twinops-live.twinops-system.svc:8080 \
  --set sampleTwin.liveAPITokenSecretRef.name=twinops-live-api
```

## Metrics

The operator itself does not expose the live MQTT metrics endpoint. When you
co-locate `twinopsctl serve`, scrape annotations are documented in `values.yaml`
(`prometheus.io/scrape` → `/metrics` on port `8080`).

## Honesty

Experimental. Not production-hardened RBAC / multi-tenant controls.
