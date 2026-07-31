# ADR-0003: Scene highlight protocol without GPU

## Status

Accepted

## Context

Milestone 6 needs an Omniverse / streaming story, but requiring Kit App Streaming
or NVCF to demo drift visualization would exclude most contributors and CI.

We still need a stable contract so:

- the web UI can show drifted prims;
- a Kit extension can later apply selection / emissive materials;
- demos remain honest about what is mock vs real GPU streaming.

## Decision

Define **`twinops.highlight.v1`** as a JSON snapshot available at `GET /api/scene`
(and on WebSocket drift/reconcile frames):

- one entry per OpenUSD prim;
- worst-case drift status aggregation;
- `highlight.enabled/color/intensity` for consumers;
- no Omniverse SDK dependency to produce or validate the payload.

A Kit extension stub polls this API. The web UI renders a mock streaming viewport
that consumes the same contract.

## Consequences

### Positive

- GPU-free demos and CI coverage for the visualization contract.
- Clear upgrade path: replace mock viewport / stub apply with real Kit commands.

### Negative / trade-offs

- Not a substitute for Kit App Streaming image quality or latency claims.
- Highlight colors are heuristic, not material-authoritative.
