# Kubernetes operator

Single-twin controller (v1.4 production-lean) that reconciles:

```text
DigitalTwin CR
   → materialize artifactSource
   → build (inline twinopsctl | isolated Job twinops-job)
   → publish immutable output revision (configmap / oci / s3)
   → drift + optional live API probe
   → status.phase / status.output / status.build / status.drift
```

## Toolchain

- Go **1.26.x** (see `go.mod` / CI `setup-go`)
- `twinopsctl` on `PATH` (or via `make install` / `--twinopsctl=`)

## Workspace (controller-owned)

The manager mounts a writable **emptyDir** at `/tmp`. Every twin uses a
**managed** path — never a free-form user absolute path for cleanup:

```text
/tmp/twinops/<namespace>/<uid>/
```

`spec.outputDir` is **legacy and ignored** for write/cleanup (avoids one CR
wiping another twin’s tree). On delete the finalizer removes only the managed
workspace plus the published `{name}-output` ConfigMap.

## Durable output (v1.4 immutable revisions)

After compose, the operator builds a **deterministic** `bundle.tar.gz` and publishes
an **immutable** revision (default ConfigMap mode):

```text
{name}-output-r{N}   # immutable: true
{name}-output        # optional mutable index (latest pointer)
```

```yaml
status:
  inputDigest: sha256:...
  output:
    uri: configmap://twinops-system/assembly-line-a-output-r2
    digest: sha256:...
    revision: 2
    mediaType: application/vnd.twinops.bundle.v1+tar+gzip
    bundleKey: bundle.tar.gz
    history: [...]
  build:
    mode: inline   # or job
    phase: Succeeded
```

Extract:

```bash
kubectl get cm assembly-line-a-output-r2 -n twinops-system \
  -o jsonpath='{.binaryData.bundle\.tar\.gz}' | base64 -d | tar -tzf -
```

Modes: `configmap` (default) · `oci` · `s3` — see [ADR-0024](adr/0024-immutable-output-revisions.md).

### Isolated Job builds (v1.4+)

```yaml
spec:
  build:
    mode: job
    activeDeadlineSeconds: 300
    # image + serviceAccountName are Helm/env only (not CR) to prevent privilege escalation
```

Requires `artifactSource.configMapName` (Job input is a ConfigMap mount; large CAD/USD
inputs should use OCI/S3 *output* and keep job inputs compact, or use `inline` + URL).

Jobs are named `{twin}-build-{execKey12}` where **execKey** hashes input digest **and**
publish destination (`mode` / repository / bucket / secrets). Changing either starts a new Job.

Job result includes structured `drift` (Synced/Detected); controller writes it to
`status.drift` even for OCI/S3 paths (no local stage). Fatal drift tool errors fail the Job
before publish.

Helm: `buildImage`, `buildServiceAccountName` (default `twinops-build`).
In `rbac.mode=namespaced`, the build SA is created **in each** `watchNamespaces` entry.
See [ADR-0023](adr/0023-isolated-build-job.md).

### OCI / S3 publish

Fail-closed by default. Set `outputPublish.allowLabFallback: true` only for lab demos
without a registry/MinIO. Production image includes `oras` and `aws`.

```bash
make operator-job-e2e
make operator-oci-s3-e2e
```

Workspace is always `/tmp/twinops/<namespace>/<uid>` (finalizer-safe).
`spec.outputDir` is ignored for cleanup.

Disable publish with `spec.outputPublish.enabled: false`. Manager flags:

```text
--build-timeout=120s
--max-concurrent-reconciles=2
```

Metrics: `twinops_reconcile_total`, `twinops_compose_duration_seconds`, `twinops_drift_findings`.

## RBAC modes

```yaml
# values.yaml
rbac:
  mode: cluster          # default ClusterRole
  # mode: namespaced
  # watchNamespaces: [factory-a, factory-b]  # empty → chart namespace only
```

Namespaced mode installs Role/RoleBinding per watched namespace and passes
`--watch-namespaces=...` so the manager cache is limited.

## In-cluster proof

```bash
# kind + docker build + helm install + restart recovery
bash scripts/operator_incluster_e2e.sh
# Job keyed by input digest + re-compose on CM update
bash scripts/operator_job_e2e.sh
# Real OCI (local registry) + S3 (MinIO) publish
bash scripts/operator_oci_s3_e2e.sh
```

## Fastest path: local cluster demo

Requires Docker + kubectl, plus **k3d** (preferred) or **kind**.

```bash
make install
make operator-demo
```

Provider selection (`TWINOPS_CLUSTER_PROVIDER`):

- `auto` (default) — k3d if installed, otherwise kind
- `k3d` / `kind` — force one provider

What it does:

1. Creates (or reuses) local cluster `twinops`
2. Applies the `DigitalTwin` CRD
3. Applies a sample CR pointing at `examples/assembly-line`
4. Runs the manager out-of-cluster
5. Waits for `status.phase` = `Ready` or `DriftDetected`

Cleanup:

```bash
make operator-demo-cleanup
```

Useful watches:

```bash
kubectl -n twinops-system get dtwin -w
kubectl -n twinops-system describe dtwin assembly-line-a
```

## Install CRD only

```bash
kubectl apply -f config/crd/bases/twinops.io_digitaltwins.yaml
```

## Run locally against an existing kubeconfig

```bash
make install
make operator-run
```

In another shell:

```bash
kubectl apply -f config/samples/namespace.yaml
kubectl apply -f config/samples/twinops_v1alpha1_digitaltwin.yaml
kubectl get digitaltwins -A
```

Prefer `spec.artifactSource` (exactly one of `configMapName` / `url`):

```yaml
spec:
  artifactSource:
    configMapName: assembly-line-inputs   # twin.yaml + optional desired/telemetry + base USDA
    # expectedDigest: sha256:...          # optional fail-closed pin
  # or: url: https://example.com/twin-bundle.tar.gz
  # outputDir is ignored — workspace is always /tmp/twinops/<ns>/<uid>
```

Materialize is **atomic** (staging dir → rename; stale files from prior bundles are
removed). HTTPS URL fetches block private/loopback hosts unless the operator sets
`TWINOPS_ARTIFACT_ALLOW_PRIVATE=1` (lab only). Set
`TWINOPS_ARTIFACT_REQUIRE_URL_DIGEST=1` (Helm: `artifactRequireURLDigest`) to require
`expectedDigest` for URL sources.

Status exposes `inputDigest` / `artifactDigest`, `workspacePath`, and `output.*`.
Verify with:

```bash
make operator-artifact-e2e      # out-of-cluster manager + bundle Stage.Open
make operator-incluster-e2e     # Helm-installed image + restart digest stability
```

## Helm

```bash
helm upgrade --install twinops-operator deploy/helm/twinops-operator \
  --namespace twinops-system --create-namespace \
  --set image.tag=1.4.2
```

Useful values: `rbac.mode`, `artifactRequireURLDigest`, `leaderElect`, `securityContext` (always on).

Image build:

```bash
docker build -f Dockerfile.operator -t ghcr.io/justrunme/twinops-operator:1.4.2 .
```

## Status phases

| Phase | Meaning |
| --- | --- |
| Composing | OpenUSD stage build in progress |
| Ready | Stage composed; drift synced or not configured |
| DriftDetected | Three-way drift present |
| Error | Compose/drift execution failed |

Printer columns include `Drift`, `Critical`, and `Findings`:

```bash
kubectl get dtwin -A
# NAME              PHASE           DRIFT      CRITICAL   FINDINGS   AGE
# assembly-line-a   DriftDetected   Detected   1          5          12s
```

`status.drift` also carries `warning`, `summary`, and `reportPath` (filesystem path to `drift-report.json`).
