# ADR-0013: Live API mTLS and demo SSO JWT

## Status

Accepted (lab / demo)

## Context

Bearer API tokens (ADR-0008) are enough for local demos. Shared binds and
cluster Services need stronger transport auth and an SSO-shaped login path
without claiming enterprise IdP completeness.

## Decision

1. **HTTPS + mTLS** via `twinopsctl serve --tls-cert/--tls-key` and optional
   `--tls-client-ca` / `--tls-require-client-cert` (lab certs from
   `scripts/gen_live_tls_certs.sh`).
2. **Demo SSO JWT**: HS256 Bearer tokens issued by `twinopsctl sso issue` and
   validated when `TWINOPS_SSO_JWT_SECRET` / `--sso-jwt-secret` is set.
   Accepted alongside the static API token.
3. **OIDC front**: optional `deploy/demo/docker-compose.oauth2-proxy.yml` shows
   the reverse-proxy shape for a real IdP; not required for the reference demo.

## Consequences

- mTLS and SSO demos stay honest (lab certs / HS256 JWT, not enterprise SSO)
- Kit WebRTC lab can sit behind HTTPS without inventing a cloud IdP
