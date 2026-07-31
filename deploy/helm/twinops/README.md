# twinops (umbrella)

Minimal umbrella chart that composes:

| Subchart / stub | Purpose |
| --- | --- |
| `twinops-operator` | DigitalTwin controller |
| `live` values stub | Documents intended live API Deployment (compose remains primary for demos) |

## Install (operator only)

```bash
make helm-deps          # refreshes charts/ from Chart.lock (gitignored packages)
make helm-template      # optional render smoke (live stub + demo token)
helm upgrade --install twinops deploy/helm/twinops \
  --namespace twinops-system \
  --create-namespace
```

## Enable sample twin + live probe

```bash
helm upgrade --install twinops deploy/helm/twinops \
  --namespace twinops-system --create-namespace \
  --set twinops-operator.sampleTwin.enabled=true \
  --set twinops-operator.sampleTwin.liveAPIURL=http://twinops-live.twinops-system.svc:8080
```

## Optional live Deployment

`live.apiToken` is stored in a Kubernetes Secret (`twinops-live-api`) and mounted
as `TWINOPS_API_TOKEN` (not passed as a container arg).

```bash
helm upgrade --install twinops deploy/helm/twinops \
  --namespace twinops-system --create-namespace \
  --set live.enabled=true \
  --set live.apiToken=demo-token
```

Demo default remains `make docker-live-up` when you do not want a cluster-side live API.
