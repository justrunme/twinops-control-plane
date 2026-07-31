# Changelog

All notable TwinOps changes are listed here. Dates are UTC.

## Unreleased

- Docs index (`docs/README.md`) + root `SECURITY.md`
- `twinopsctl health` / `make health` for live API probes
- `make mqtt-up` / `make mqtt-down` Mosquitto shortcuts
- Dependabot + CODEOWNERS + issue/PR templates

## 2026-07-31

- Live control plane: spike → reconcile → SYNCED demo (`make live-demo`)
- Bidirectional MQTT publish + ingest (`make mqtt-smoke`)
- Scene highlight protocol `twinops.highlight.v1` (`GET /api/scene`, `twinopsctl scene`)
- Mock Kit streaming viewport in the web UI
- Mock PLM adapter CLI (`twinopsctl plm …`, `make plm-demo`)
- k3d/kind DigitalTwin operator demo (`make operator-demo`)
- Live metrics JSON + Prometheus (`/api/metrics`, `/metrics`)
- Live HTML drift report (`GET /api/drift/report`)
- `twinopsctl doctor` local prerequisite checks
- Local gate `make verify-all`
- ADRs for highlight protocol and MQTT bridge
- CONTRIBUTING + security notes refresh
- CHANGELOG
