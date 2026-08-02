# TwinOps 1.4.1 — Immutable outputs + isolated Jobs

Date: 2026-08-02 (UTC)

## Intent

Graduate the single-twin pilot toward **production-lean** execution:

1. **Immutable output revisions** (ConfigMap / OCI / S3)
2. **Isolated compose** via Kubernetes Job + sandbox securityContext

v1.4.1 hardens the paths introduced in 1.4.0 so the README claim is accurate end-to-end.

## Spec

```yaml
spec:
  build:
    mode: job          # or inline (default)
    activeDeadlineSeconds: 300
    cpuRequest: 100m
    cpuLimit: "1"
    memoryRequest: 128Mi
    memoryLimit: 512Mi
    # image / serviceAccountName are NOT CR fields — set via Helm:
    #   buildImage, buildServiceAccountName
  outputPublish:
    mode: configmap    # configmap | oci | s3
    keepRevisions: 5
    allowLabFallback: false   # fail-closed default
    # oci:
    #   repository: ghcr.io/org/twinops-artifacts
    #   registrySecretRef: { name: regcred }
    # s3:
    #   s3Bucket: twins
    #   s3Endpoint: https://minio.example
    #   s3PathStyle: true
    #   s3SecretRef: { name: s3creds }
```

## Status

```yaml
status:
  build:
    mode: job
    jobName: assembly-line-a-build-a81f94c2aaaa   # keyed by input digest
    phase: Succeeded
  output:
    uri: oci://ghcr.io/org/twinops-artifacts@sha256:…
    digest: sha256:…          # TwinOps content digest
    revision: 2
    history: […]
```

## Job flow

```text
Controller materialize (SSRF policy) → input digest D
  → Job {twin}-build-{D12} (twinops-job)
       configmap mode: result CM carries bundle → controller mints output-rN
       oci/s3 mode: Job pushes directly → result CM is metadata-only
  → status.output + history
```

Changing the input ConfigMap (same CR generation) creates a **new** Job because the name includes the input digest.

## Correctness (1.4.1)

| Item | Behavior |
|------|----------|
| Job key | input digest, not generation |
| OCI/S3 default | fail-closed; lab fallback only with `allowLabFallback` |
| Image clients | `oras` + `aws` in operator image |
| Auth | `DOCKER_CONFIG` from `registrySecretRef` |
| OCI URI | `oci://repo@sha256:<manifest-digest>` |
| Large stages | Job publishes to OCI/S3 (no ConfigMap bridge) |
| Privilege | no CR `build.image` / `build.serviceAccountName` |
| Namespaced RBAC | `twinops-build` SA per watched namespace |
| Result CMs | OwnerReference + finalizer cleanup |

## Proof

```bash
make go-test
make operator-incluster-e2e   # ConfigMap immutable revisions
make operator-job-e2e         # Job re-key on input update
make operator-oci-s3-e2e      # local registry + MinIO
```

## Limits (honest)

- Job mode requires `artifactSource.configMapName`.
- Still single-twin oriented; not multi-tenant plant platform.
- Multi-site SLA / fleet orchestration is out of scope.

See ADR-0023, ADR-0024.
