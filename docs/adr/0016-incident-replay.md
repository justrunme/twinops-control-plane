# ADR-0016: Twin incident history and replay

## Status

Accepted

## Context

Live demos produce a timeline (healthy → spike → drift → reconcile → recover).
For portfolio and debugging we need that narrative as a durable artifact, and a
way to re-run drift against it without a live MQTT stream.

## Decision

1. Define `TwinIncident` JSON (`apiVersion: twinops.io/v1alpha1`).
2. Export from live `/api/timeline` or a timeline file via `twinopsctl incident export`.
3. Replay with `twinopsctl incident replay` — merge step observation deltas into
   base observed JSON and re-run `detect_drift` per step.
4. Keep the web timeline UI as the interactive view; incident JSON is the
   portable history (Git-history-like for twins).

## Consequences

- Spike demos become shareable fixtures (`examples/.../incident-*.json`)
- No new product surface explosion — one `incident` command family
- Richer UI timeline visualization can consume the same model later
