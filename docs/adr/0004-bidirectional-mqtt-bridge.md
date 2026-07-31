# ADR-0004: Bidirectional MQTT bridge

## Status

Accepted

## Context

Industrial telemetry usually arrives over MQTT (or similar). TwinOps already had
an in-process simulator and an optional publish bridge. Portfolio demos need to
show the reverse path: factory PLC → broker → observed twin → drift.

## Decision

When `--mqtt-host` is set:

1. **Publish** simulator events to mapped topics with `"source": "twinops"`.
2. **Ingest** the same topic set via a separate MQTT client (`twinops-ingest`).
3. Ignore TwinOps publish echoes by `source` to prevent feedback loops.
4. Lock overridden simulator fields so ticks do not immediately overwrite PLC values.
5. Clear ingest overrides on reconcile / heal.

Disable ingest with `--no-mqtt-ingest` when only outbound publish is desired.

## Consequences

### Positive

- End-to-end Mosquitto smoke proves PLC inject → CRITICAL drift.
- Keeps the in-process simulator usable offline.

### Negative / trade-offs

- Demo broker is anonymous (`allow_anonymous true`) — not for production.
- Topic map currently comes from the DigitalTwin manifest only.
