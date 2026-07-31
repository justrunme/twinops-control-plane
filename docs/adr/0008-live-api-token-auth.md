# ADR-0008: Optional live API bearer token

## Status

Accepted (2026-07-31)

## Context

The live control plane exposes spike/reconcile actions. Binding to localhost
is the default mitigation, but compose demos bind `0.0.0.0` and need a simple
authn switch before any shared exposure.

## Decision

- If `TWINOPS_API_TOKEN` (or `--api-token`) is set, require
  `Authorization: Bearer <token>` or `X-TwinOps-Token` for `/api/*` and `/ws/*`
- Keep `/api/health`, `/api/ready`, and `/metrics` public for probes
- If unset, auth stays disabled (local demo default)

## Consequences

- Demo compose can set a token without claiming enterprise SSO
- CLI live helpers should pass the token when configured
- Static UI assets remain reachable so the SPA can load (API calls still gated)
