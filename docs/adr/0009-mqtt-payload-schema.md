# ADR-0009: Versioned MQTT telemetry payload schema

## Status

Accepted (2026-07-31)

## Context

Topic catalog (ADR-0006) defines *where* telemetry lands. Payload shape was still
ad-hoc JSON from the simulator / PLC mocks, which makes ingest validation hard.

## Decision

- Introduce `schemas/twinops.mqtt.payload.v1.json` with required
  `schema`, `topic`, `value`, `timestamp`
- Provide `validate_mqtt_payload` helpers and `twinopsctl mqtt validate`
- Keep simulator compatible; new publishers should emit the schema field

## Consequences

- Scripts can reject malformed PLC traffic before it mutates observed state
- Future ACL/TLS work can assume a stable payload envelope
- Older payloads without `schema` fail validation (intentional for new tools)
