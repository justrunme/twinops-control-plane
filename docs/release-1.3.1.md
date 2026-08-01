# TwinOps 1.3.1 — Pilot correctness patch

Date: 2026-08-02 (UTC)

## Why

`v1.3.0` shipped durable *status* fields and in-cluster E2E, but the published
ConfigMap payload was incomplete (no `assets/`) and non-deterministic
(`reconciliation-report.json` timestamps). Security fixes on `main` also landed
*after* the `v1.3.0` tag — this patch re-tags a green, complete pilot.

## Fixes

| Item | Change |
|------|--------|
| Output bundle | Deterministic `bundle.tar.gz` with recursive USDA + `assets/` |
| Content digest | Excludes volatile reports; stable across rebuild/restart |
| E2E | Extract bundle + `Usd.Stage.Open` (pxr) + restart digest/revision equality |
| Workspace | Always `/tmp/twinops/<ns>/<uid>`; finalizer never `RemoveAll(spec.outputDir)` |
| Helm | `artifactRequireURLDigest`, `securityContext`, `leaderElect` |
| Security | Trivy also scans streaming-sidecar image |

## Upgrade from 1.3.0

1. Upgrade operator image/chart to `1.3.1`.
2. Output ConfigMaps switch from loose files → `binaryData.bundle.tar.gz` (recreate on next reconcile).
3. Consumers must extract the tarball (not individual keys).

See [ADR-0022](adr/0022-deterministic-output-bundle.md).
