# ADR-0024: Immutable output revisions (ConfigMap history, OCI, S3)

## Status

Accepted for TwinOps **v1.4**.

## Context

v1.3.1 published `bundle.tar.gz` into a single ConfigMap `{name}-output`, overwriting
prior content. `revision` incremented but old blobs were not retained — no rollback.

## Decision

1. `spec.outputPublish.mode`:
   - `configmap` (default): write **immutable** ConfigMap `{name}-output-r{N}` with
     `immutable: true`. Keep last `keepRevisions` (default 5). Latest pointer
     annotation on a mutable `{name}-output` index ConfigMap (optional) or status only.
   - `oci`: push via ORAS to `repository` as tag `rev-{N}` and digest reference;
     `status.output.uri = oci://host/repo@sha256:…`.
   - `s3`: PUT object `s3://bucket/prefix/{ns}/{name}/r{N}/bundle.tar.gz`;
     URI includes digest query.
2. `status.output.history[]` retains recent revisions (digest, uri, inputDigest, publishedAt).
3. Content digest remains the deterministic content hash from ADR-0022.
4. Same content digest → do not create a new revision (idempotent publish).

## Consequences

- True rollback: point consumer at previous `uri`.
- ConfigMap mode stays registry-free for kind/lab.
- OCI/S3 need credentials (Secret refs) for real clusters.
