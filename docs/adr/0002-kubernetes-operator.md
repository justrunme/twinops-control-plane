# ADR-0002: Kubernetes DigitalTwin operator

## Status

Accepted

## Context

Milestones 1–2 provide a local compiler and drift engine. To demonstrate GitOps-style continuous reconciliation we need a Kubernetes control loop that treats digital twins as declarative resources.

## Decision

Implement a Go controller-runtime operator with a `DigitalTwin` CRD that shells out to `twinopsctl` for compose/drift. This reuses the Python OpenUSD toolchain instead of reimplementing composition in Go.

## Consequences

- Fast path to a working reconcile loop.
- Operator image must include (or sidecare) `twinopsctl`.
- Later we can replace exec calls with in-process gRPC/Python worker if needed.
