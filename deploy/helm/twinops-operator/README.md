# twinops-operator Helm chart

Installs the TwinOps Kubernetes operator that reconciles `DigitalTwin` CRs.

## Prerequisites

- Kubernetes 1.27+ (k3d/kind work for demos)
- CRDs bundled under `crds/`

## Install

```bash
helm upgrade --install twinops-operator deploy/helm/twinops-operator \
  --namespace twinops-system \
  --create-namespace
```

Prefer `spec.artifactSource` (ConfigMap / HTTP bundle) over hostPath `manifestPath`.

## Values

| Key | Default | Notes |
| --- | --- | --- |
| `image.repository` | `ghcr.io/justrunme/twinops-operator` | Build via `Dockerfile.operator` |
| `image.tag` | `1.2.0` | Keep in sync with Chart `appVersion` |
| `twinopsctlPath` | `/usr/local/bin/twinopsctl` | Path inside the manager container |
| `examples.enabled` | `false` | Optional hostPath mount for local demos |
| `sampleTwin.enabled` | `false` | Optionally install a demo DigitalTwin CR |
| `sampleTwin.artifactSource.configMapName` | `""` | Preferred input source |
| `sampleTwin.liveAPIURL` | `""` | Populate `status.live` via live API probe |

```bash
kubectl -n twinops-system create configmap assembly-line-inputs \
  --from-file=twin.yaml=examples/assembly-line/twin.yaml \
  --from-file=desired.yaml=examples/assembly-line/desired.yaml \
  --from-file=telemetry.json=examples/assembly-line/telemetry.json

helm upgrade --install twinops-operator deploy/helm/twinops-operator \
  --namespace twinops-system --create-namespace \
  --set sampleTwin.enabled=true \
  --set sampleTwin.artifactSource.configMapName=assembly-line-inputs \
  --set sampleTwin.liveAPIURL=http://twinops-live.twinops-system.svc:8080
```

Status reports `artifactDigest` (sha256 of materialized inputs).
