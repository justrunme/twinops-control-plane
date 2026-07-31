# Kubernetes operator

Experimental DigitalTwin controller that reconciles:

```text
DigitalTwin CR
   → twinopsctl build
   → twinopsctl drift (optional)
   → status.phase / status.drift
```

## Install CRD

```bash
kubectl apply -f config/crd/bases/twinops.io_digitaltwins.yaml
```

## Run locally (no image build)

```bash
make install
make operator-run
```

In another shell (with kubeconfig pointing at a cluster):

```bash
kubectl apply -f config/rbac/service_account.yaml
kubectl apply -f config/rbac/role.yaml
kubectl apply -f config/rbac/role_binding.yaml
kubectl apply -f config/samples/twinops_v1alpha1_digitaltwin.yaml
kubectl get digitaltwins -A
```

For the sample CR, mount/copy `examples/assembly-line` to the paths referenced in `spec.manifestPath`.

## Helm

```bash
helm upgrade --install twinops-operator deploy/helm/twinops-operator
```

Image build:

```bash
docker build -f Dockerfile.operator -t ghcr.io/justrunme/twinops-operator:0.1.0 .
```

## Status phases

| Phase | Meaning |
| --- | --- |
| Composing | OpenUSD stage build in progress |
| Ready | Stage composed; drift synced or not configured |
| DriftDetected | Three-way drift present |
| Error | Compose/drift execution failed |
