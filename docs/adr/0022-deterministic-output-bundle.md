# ADR-0022: Deterministic ConfigMap output bundle (v1.3.1)

## Status

Accepted for TwinOps **v1.3.1**.

## Context

v1.3.0 published top-level files only and included `reconciliation-report.json`
(with `generatedAt` / absolute paths). That meant:

1. `assets/root.usda` was missing → `Usd.Stage.Open(root.usda)` failed after extract.
2. Rebuild of identical input produced a new content digest → revision churn.

## Decision

1. Publish a single **deterministic** `bundle.tar.gz` (zero mtime, sorted entries).
2. Include recursive USDA content + `assets/**`; exclude `inputs/`, `drift/`,
   `reconciliation-report.json`.
3. Content digest = sha256 over sorted relative path + payload (not wall-clock).
4. Status:

```yaml
output:
  uri: configmap://ns/name
  digest: sha256:...
  revision: N
  mediaType: application/vnd.twinops.bundle.v1+tar+gzip
  bundleKey: bundle.tar.gz
  stageKey: root.usda
```

5. E2E extracts the bundle and runs `Usd.Stage.Open` when pxr is available.
6. Controller workspace is always `/tmp/twinops/<namespace>/<uid>`; finalizer only
   deletes that path (never user `spec.outputDir`).

## Consequences

- Durable output is stage-complete and digest-stable across restarts.
- ConfigMap size budget still applies (~900 KiB); large assets need OCI later (v1.4).
