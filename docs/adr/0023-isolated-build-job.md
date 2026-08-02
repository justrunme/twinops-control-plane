# ADR-0023: Isolated twin builds via Kubernetes Jobs

## Status

Accepted for TwinOps **v1.4**.

## Context

v1.3 ran `twinopsctl build|drift` inside the controller manager process. A heavy or
pathological composition could exhaust memory/CPU of the whole operator Pod.

## Decision

1. `spec.build.mode` is `inline` (default, lab) or `job` (pilot/production).
2. In `job` mode the controller:
   - materializes inputs (still in-controller — network SSRF policy stays centralized);
   - creates a one-shot Job `{name}-build-{generation}` with sandbox securityContext,
     resource requests/limits, and `activeDeadlineSeconds`;
   - Job runs `twinopsctl build` + optional `drift` and writes a result ConfigMap
     `{name}-build-result-{generation}` (bundle + result.json);
   - controller watches Job completion, publishes durable output, updates status.
3. Jobs use TTL after finish; result ConfigMaps are deleted after successful publish.
4. Manager never executes twinopsctl when `mode=job`.

## Consequences

- Compose failures isolate to the Job Pod.
- Requires RBAC for batch/jobs + result ConfigMaps.
- Kind E2E covers job mode without external registries.
