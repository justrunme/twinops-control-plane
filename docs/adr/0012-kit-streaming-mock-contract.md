# ADR-0012: Kit streaming mock contract

## Status

Accepted (foundation)

## Context

Milestone 6 needs a path toward Kit App Streaming / browser WebRTC without
forcing a GPU for demos. The highlight protocol (`twinops.highlight.v1`) already
works CPU-first. Callers need a stable session descriptor shape so a real
streaming provider can replace the mock later.

## Decision

`GET /api/streaming/session` returns `KitStreamingSession` with:

| Field | Mock today | Future |
| --- | --- | --- |
| `spec.sceneUrl` | `/api/scene` | same |
| `spec.eventsUrl` | `/ws/events` | same |
| `spec.streamUrl` | `null` | authenticated WebRTC / Kit signaling URL |
| `spec.webrtc` | `{ enabled: false, … }` | offer/answer signaling hints |
| `metadata.mode` | `mock` | `kit-app-streaming` / provider id |

Web UI keeps the mock viewport until `streamUrl` is non-null.

## Consequences

- Demo credibility without NVCF / cloud GPU
- Clear upgrade seam for a real Kit App Streaming adapter
- No claim that WebRTC works today
