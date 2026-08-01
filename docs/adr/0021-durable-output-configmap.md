# ADR-0021: Durable twin output via ConfigMap (pilot)

## Status

Accepted for TwinOps **v1.3** pilot.

## Context

`status.stagePath` pointed at a path inside the operator Pod (`/tmp/twinops/...`).
After Pod restart the file disappeared; no other workload could reference the
composed OpenUSD bundle immutably.

## Decision

1. After a successful `twinopsctl build`, publish top-level stage files into a
   ConfigMap named `{digitaltwin}-output` in the same namespace.
2. Record durable metadata on status:

```yaml
status:
  inputDigest: sha256:...
  output:
    digest: sha256:...
    uri: configmap://namespace/name
    revision: 1
    stageKey: root.usda
```

3. Default publish **on** (`spec.outputPublish.enabled` defaults true). Mode is
   only `configmap` in v1.3; OCI/S3 remain future modes.
4. OwnerReference links the ConfigMap to the DigitalTwin; finalizer also deletes it.
5. Build is skipped when `generation` + `inputDigest` match and local stage still exists;
   drift still re-runs each interval.

## Consequences

- Pilot twins (demo USDA sizes) get cluster-durable, digest-addressable outputs.
- ConfigMap 1 MiB soft limit: large assets must use hostPath/PVC or future OCI mode.
- Consumers mount ConfigMap or fetch by `status.output.uri` without speaking to the operator Pod FS.
