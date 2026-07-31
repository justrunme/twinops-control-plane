# Security Policy

TwinOps is an **experimental** reference architecture. Do not expose the live demo API or the anonymous Mosquitto compose stack to the public internet.

## Reporting a vulnerability

Open a private GitHub security advisory on
[justrunme/twinops-control-plane](https://github.com/justrunme/twinops-control-plane)
or email the maintainer listed in the GitHub profile.

Please include:

1. Affected component (CLI, live API, MQTT bridge, operator, web UI)
2. Reproduction steps
3. Impact assessment

## Current demo posture

Full notes: [docs/security.md](docs/security.md).

- Live API binds to `127.0.0.1` by default
- MQTT demo broker is anonymous / no TLS (local only)
- Mock PLM catalog — no vendor credentials
- No production / compliance claims
