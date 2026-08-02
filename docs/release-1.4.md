# TwinOps 1.4.0 — Immutable outputs + isolated Jobs

Date: 2026-08-02 (UTC)

## Intent

Graduate the single-twin pilot toward **production-lean** execution:

1. **Immutable output revisions** (ConfigMap / OCI / S3)
2. **Isolated compose** via Kubernetes Job + sandbox securityContext

## Spec additions

```yaml
spec:
  build:
    mode: job          # or inline (default)
    activeDeadlineSeconds: 300
    cpuRequest: 100m
    cpuLimit: "1"
    memoryRequest: 128Mi
    memoryLimit: 512Mi
    image: ghcr.io/justrunme/twinops-operator:1.4.0
  outputPublish:
    mode: configmap    # configmap | oci | s3
    keepRevisions: 5
    # oci:
    #   repository: ghcr.io/org/twinops-artifacts
    #   registrySecretRef: { name: regcred }
    # s3:
    #   s3Bucket: twins
    #   s3Endpoint: https://minio.example
    #   s3SecretRef: { name: s3creds }
```

## Status

```yaml
status:
  build:
    mode: job
    jobName: assembly-line-a-build-3
    phase: Succeeded
  output:
    uri: configmap://twinops-system/assembly-line-a-output-r2
    digest: sha256:…
    revision: 2
    history:
      - revision: 1
        uri: configmap://…/assembly-line-a-output-r1
        digest: sha256:…
      - revision: 2
        uri: configmap://…/assembly-line-a-output-r2
        digest: sha256:…
```

## Job flow

```text
Controller materialize (SSRF policy)
  → Job twinops-job (build + drift + result ConfigMap)
  → Controller publish durable revision (configmap/oci/s3)
  → status.output + history
```

## Limits (honest)

- OCI/S3 require credentials + `oras`/`aws` on the manager when not using lab fallback.
- Job mode requires `artifactSource.configMapName` (URL sources use `inline` or pre-stage to CM).
- Still single-twin oriented; not multi-tenant plant platform.

See ADR-0023, ADR-0024.
