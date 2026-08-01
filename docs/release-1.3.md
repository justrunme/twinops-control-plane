# TwinOps 1.3.0 — Single-twin pilot ready

Date: 2026-08-01 (UTC)

## Intent

Graduate TwinOps from “strong reference demo” to a **single-twin pilot control plane**:

```text
helm install
 → apply artifact + DigitalTwin
 → output artifact published (configmap://…)
 → drift detected / synced
 → source updated → new input digest
 → operator restarted → state recovered
```

## Highlights

| Area | What shipped |
|------|----------------|
| Output | ConfigMap `{name}-output` + `status.output.{uri,digest,revision}` |
| Reconcile | Build timeout, max concurrency, generation+inputDigest idempotency |
| Ops | Prometheus metrics, Kubernetes Events, finalizer cleanup |
| RBAC | `cluster` or `namespaced` (+ `watchNamespaces`) |
| Proof | Out-of-cluster artifact E2E **and** in-cluster Helm E2E with restart |
| Supply chain | govulncheck, npm audit, Trivy, Syft SBOM (security workflow) |

## Install (pilot)

```bash
docker build -f Dockerfile.operator -t ghcr.io/justrunme/twinops-operator:1.3.0 .
# load into kind or push to registry

helm upgrade --install twinops-operator deploy/helm/twinops-operator \
  --namespace twinops-system --create-namespace \
  --set image.tag=1.3.0 \
  --set image.pullPolicy=IfNotPresent
```

Namespaced mode:

```bash
helm upgrade --install twinops-operator deploy/helm/twinops-operator \
  --namespace twinops-system --create-namespace \
  --set rbac.mode=namespaced \
  --set rbac.watchNamespaces={twinops-system}
```

## Definition of Done (verified in CI)

- [x] kind + Helm-installed operator image
- [x] ConfigMap artifact → DigitalTwin → Ready/DriftDetected
- [x] `status.output.uri` present
- [x] ConfigMap update → new input digest
- [x] Operator Pod restart → successful re-reconcile

## Explicit non-goals (still)

- Multi-tenant / multi-site plant platform
- OCI/S3 output modes (ConfigMap first)
- Multi-user GPU Kit streaming / NVCF
- Vendor PLM SDKs

## Upgrade from 1.2.x

1. Apply CRD (new status fields are additive).
2. Upgrade Helm chart / image to `1.3.0`.
3. ConfigMap RBAC already includes create/update/delete (from 1.2.1).
4. Existing twins get `status.output` on next successful compose.

See [upgrade.md](upgrade.md), [operator.md](operator.md), ADR-0021.
