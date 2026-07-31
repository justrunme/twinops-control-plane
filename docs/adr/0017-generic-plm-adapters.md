# ADR-0017: Generic File and REST PLM adapters

## Status

Accepted

## Context

TwinOps needs PLM revision/lifecycle data for composition and drift, but must not
embed proprietary Teamcenter/Windchill SDKs. Demos already use a JSON catalog
(`MockPlmAdapter`). Reviewers asked for a clear, reusable adapter surface.

## Decision

1. Keep `PlmAdapter` as the vendor-neutral protocol.
2. Ship **FilePlmAdapter** — JSON catalog on disk (same shape as today's mock).
3. Ship **RestPlmAdapter** — `GET /items`, `GET /items/{id}`, optional `PUT /items/{id}`
   with a generic item document (`id`, `revision`, `lifecycle`, `metadata`).
4. Leave Teamcenter/Windchill as stubs only; integrators implement the protocol
   or wrap REST behind their own gateway.

## Consequences

- Anyone can point TwinOps at a file or a thin REST façade without vendor SDKs
- CLI supports `--catalog` and `--url` on `twinopsctl plm *`
- Proprietary connectors stay out of core
