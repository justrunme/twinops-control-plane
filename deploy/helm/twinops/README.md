# twinops (umbrella)

Umbrella chart that composes:

| Component | Purpose |
| --- | --- |
| `twinops-operator` | DigitalTwin controller |
| `live` Deployment | Optional TwinOps live API + web UI (`Dockerfile.live`) |

Image ENTRYPOINT is `twinopsctl`; Deployment `args` start with `serve` only.

## Install (operator only)

```bash
make helm-deps
make helm-template
helm upgrade --install twinops deploy/helm/twinops \
  --namespace twinops-system \
  --create-namespace
```

## Live API + operator

```bash
helm upgrade --install twinops deploy/helm/twinops \
  --namespace twinops-system --create-namespace \
  --set live.enabled=true \
  --set live.apiToken=demo-token
```

`live.apiToken` is stored in Secret `twinops-live-api` as `TWINOPS_API_TOKEN`.

## Sample twin via ConfigMap artifact

```bash
kubectl -n twinops-system create configmap assembly-line-inputs \
  --from-file=twin.yaml=examples/assembly-line/twin.yaml \
  --from-file=desired.yaml=examples/assembly-line/desired.yaml \
  --from-file=telemetry.json=examples/assembly-line/telemetry.json

helm upgrade --install twinops deploy/helm/twinops \
  --namespace twinops-system --create-namespace \
  --set twinops-operator.sampleTwin.enabled=true \
  --set twinops-operator.sampleTwin.artifactSource.configMapName=assembly-line-inputs \
  --set twinops-operator.sampleTwin.liveAPIURL=http://twinops-live.twinops-system.svc:8080
```

Deploy smoke (CI): `make deploy-smoke`.
