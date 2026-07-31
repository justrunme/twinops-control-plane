# Security notes

## Current posture

- Compiler / drift / PLM mock are local filesystem tools — no cloud credentials required.
- Live API (`twinopsctl serve`) binds to `127.0.0.1` by default for demos.
- MQTT demo broker is intentionally anonymous for local smoke tests only.
- TwinOps MQTT publish payloads are tagged `source: twinops` so ingest can ignore echoes.
- Generated USDA / reports are plain text suitable for Git review — do not embed secrets.
- Kubernetes operator uses namespaced `DigitalTwin` CRs; Helm chart expects least-privilege SA (review before cluster install).

## Threat notes for demos

| Surface | Risk | Mitigation in this repo |
| --- | --- | --- |
| Live HTTP API | Unauthenticated control actions (spike/reconcile) | Bind localhost; set `TWINOPS_API_TOKEN` / `--api-token` before shared binds |
| `Dockerfile.live` | Image entrypoint binds `0.0.0.0:8080` | Local/demo compose only; put a proxy/auth in front if shared |
| `docker-compose.live.yml` | Publishes `:8080` + anonymous MQTT | Local demos only; do not expose to the internet |
| MQTT Mosquitto demo | Open publish/subscribe | Local compose only; no TLS; not for prod |
| MQTT ACL profile | Shared lab passwords | `docker-compose.mqtt-acl.yml` still lab-only; do not reuse passwd files outside demos |
| MQTT TLS lab stub | Self-signed cert + anonymous | `docker-compose.mqtt-tls.yml` on `:8883`; certs gitignored; not a CA/PKI story |
| Kit / streaming mock | Fake viewport may be mistaken for real GPU stream | Docs mark mock / no NVCF claims |
| PLM catalog | Accidental commit of vendor secrets | Mock JSON only; no proprietary SDKs |

## Upcoming controls

| Area | Plan |
| --- | --- |
| GitOps | PR review for twin revisions and overlay layers |
| Operator | RBAC-limited ServiceAccount, namespaced CRDs |
| Object storage | Signed URLs / least-privilege IAM |
| Streaming | Authenticated session API, idle timeout |
| Telemetry | Lab TLS+ACL demos shipped; production CA/client certs later; no secrets in USD layers |
| Supply chain | CI checks, pinned Actions, SBOM later |
| Live API | Bearer token (ADR-0008); SSO JWT + HTTPS/mTLS lab path (ADR-0013); operator SecretRef |

## Lab HTTPS / mTLS / SSO

```bash
./scripts/gen_live_tls_certs.sh
twinopsctl serve --example examples/assembly-line \
  --tls-cert deploy/demo/live-certs/server.crt \
  --tls-key deploy/demo/live-certs/server.key \
  --tls-client-ca deploy/demo/live-certs/ca.crt \
  --tls-require-client-cert \
  --sso-jwt-secret demosecret \
  --webrtc
export TWINOPS_SSO_JWT_SECRET=demosecret
twinopsctl sso issue --subject demo-user
```

Optional OIDC reverse-proxy shape: `deploy/demo/docker-compose.oauth2-proxy.yml`.

## Explicit non-goals for now

- Do not embed employer-specific PLM API credentials or proprietary schemas.
- Do not claim enterprise SSO / compliance certifications.
- Do not claim production-hardened MQTT or streaming security.
