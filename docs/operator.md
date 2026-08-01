# Kubernetes operator

Experimental DigitalTwin controller that reconciles:

```text
DigitalTwin CR
   → twinopsctl build
   → twinopsctl drift (optional)
   → optional live API probe (spec.liveAPIURL)
   → status.phase / status.drift / status.live
```

## Toolchain

- Go **1.26.x** (see `go.mod` / CI `setup-go`)
- `twinopsctl` on `PATH` (or via `make install` / `--twinopsctl=`)

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

Prefer immutable inputs via `spec.artifactSource`:

```yaml
spec:
  artifactSource:
    configMapName: assembly-line-inputs   # keys: twin.yaml, desired.yaml, telemetry.json
  # or: url: https://example.com/twin-bundle.tar.gz
  outputDir: /tmp/twinops/assembly-line-a
```

Status exposes `artifactDigest` (`sha256:...`) and `workspacePath` after materialize.
Legacy `manifestPath` / hostPath remains for local demos only.

## Helm

```bash
helm upgrade --install twinops-operator deploy/helm/twinops-operator
```

Image build:

```bash
docker build -f Dockerfile.operator -t ghcr.io/justrunme/twinops-operator:1.2.0 .
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
