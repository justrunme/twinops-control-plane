# ADR-0018: Productization end-to-end scenario

## Status

Accepted

## Context

Milestones 0.7–0.9 delivered Kit runtime, incident replay, and generic PLM
adapters as separate surfaces. Portfolio value now depends on proving they form
one operational lifecycle, with persistence across restarts and CI coverage.

## Decision

1. Ship `make e2e-demo` as the canonical one-command scenario.
2. Persist timeline / proposals / audit in optional SQLite (`twinopsctl serve --db`).
3. Add `incident replay --verify` against `expectedFinalState` /
   `expectedCriticalDrifts`.
4. Contract-test File and REST PLM adapters for interchangeable behavior.
5. Harden Kit highlight apply as a session-layer state machine (source assets
   never rewritten).

## Consequences

- CI runs the E2E demo and uploads artifacts
- v0.11 GPU streaming sidecar can assume a stable control-plane loop
- 1.0 waits for streaming + ops checklist, not for more feature sprawl
