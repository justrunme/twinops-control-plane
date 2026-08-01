# TwinOps 1.2.1 — correctness patch

Date: 2026-08-01 (UTC)

## Intent

Ship post-`1.2.0` hardening that landed on `main` (media honesty, atomic artifacts,
operator ConfigMap E2E, Helm sample path) **without** new product claims.

## Highlights

| Area | Change |
|------|--------|
| Media | Explicit `ingestEncoder` / `webrtcEncoder` / `mediaPath`; real frame receive tests |
| Artifacts | Atomic materialize, digest, SSRF, size limits with fail-closed errors |
| Operator | ConfigMap watch; kind artifact E2E; finalizer workspace cleanup |
| Helm | Sample `outputDir` under `/tmp/twinops` (matches emptyDir mount) |

## Upgrade

```bash
# charts / images still appVersion 1.2.x — pin tag 1.2.1 when published
helm upgrade twinops-operator deploy/helm/twinops-operator \
  --set image.tag=1.2.1
```

No CRD breaking changes. Additive ConfigMap RBAC verbs (create/update/delete) for
future output publish and finalizer cleanup.

## Not in 1.2.1

- Durable output URI (planned 1.3)
- In-cluster Helm operator E2E (planned 1.3)
- Namespace-scoped RBAC mode (planned 1.3)
- End-to-end NVENC RTP / multi-user Kit streaming
