# ADR-0006: Shared MQTT topic catalog

## Status

Accepted

## Context

Assembly-line demos publish and ingest the same factory topics. Duplicating the
topic → prim map across docs, smoke scripts, and API responses drifts over time.

## Decision

Keep a single in-code catalog (`python/twinops/telemetry/topics.py`) and mirror
it for humans in `examples/assembly-line/mqtt-topics.json`.

Expose the catalog through:

- `GET /api/mqtt/topics` (includes live MQTT status when the server is up)
- `twinopsctl mqtt topics` / `make mqtt-topics`

Echo suppression stays based on payload `source` ∈ {`twinops`, `twinops-bus`,
`twinops-simulator`} (ADR-0004).

## Consequences

### Positive

- One place to extend demo topics
- Smoke / UI / docs stay aligned

### Negative / trade-offs

- Example JSON can drift if not regenerated — use
  `python scripts/sync_mqtt_topics.py` (and `--check` in CI / `verify_all`)
