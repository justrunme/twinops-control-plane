# ADR-0010: Apply verification via rebuild + re-drift

## Status

Accepted (2026-07-31)

## Context

Local `twinopsctl apply` copies proposal artifacts onto a branch, but demos still
needed a manual rebuild/drift pass to prove the overlay improves the twin.

## Decision

Add `twinopsctl apply --verify` which:

1. Applies proposal artifacts locally (existing behavior)
2. Re-composes the DigitalTwin into a temp stage
3. Injects `reconcile-overlay.usda` into that stage
4. Re-runs three-way drift against desired/observed
5. Returns non-zero when `hasDrift` remains true

Remote PR automation stays out of scope; `--print-pr` remains advisory.

## Consequences

- `make apply-verify` gives a one-command GitOps demo close-out
- Verification uses a temp stage and does not mutate the proposal branch layout
- Empty overlays may still report drift from sample telemetry (expected)
