# Security notes

## Current posture (Milestone 0–1)

- No network services are started by the compiler.
- Manifests and USDA files are local filesystem inputs.
- No credentials, cloud tokens, or vendor PLM secrets are required.
- Generated artifacts are deterministic text suitable for Git review.

## Upcoming controls

| Area            | Plan                                              |
| --------------- | ------------------------------------------------- |
| GitOps          | PR review for twin revisions and overlay layers   |
| Operator        | RBAC-limited ServiceAccount, namespaced CRDs      |
| Object storage  | Signed URLs / least-privilege IAM                 |
| Streaming       | Authenticated session API, idle timeout           |
| Telemetry       | TLS MQTT, topic ACL, no secrets in USD layers     |
| Supply chain    | CI checks, pinned Actions, SBOM later             |

## Explicit non-goals for now

- Do not embed employer-specific PLM API credentials or proprietary schemas.
- Do not claim enterprise SSO / compliance certifications.
