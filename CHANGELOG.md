# Changelog

All notable TwinOps changes are listed here. Dates are UTC.

## Unreleased

## 0.3.2 — 2026-07-31

- `schemas/twinops.highlight.v1.json` + `twinopsctl scene --strict` (also `make scene`)
- `twinopsctl proposal` / `make proposal` + README DX refresh
- `twinopsctl timeline` / `make timeline`
- `Dockerfile.live` + Go 1.26 operator image base; UI hotkeys 1/2
- `twinopsctl serve --open` + `scripts/sync_mqtt_topics.py` / CI catalog check
- ADR-0006 MQTT topic catalog + `make version`
- Drift CSV export (`drift-report.csv`, `--csv`, `GET /api/drift/csv`)
- `make mqtt-topics`
- CI Go toolchain 1.26.x (matches go.mod after controller-runtime bump)
- Dependabot ignores isolated major bumps for k8s.io/* / controller-runtime
- Live-demo smoke asserts `/api/ready` + `/api/scene/report`
- `workflow_dispatch` for CI

## 0.3.1 — 2026-07-31

- Live `GET /api/ready` readiness probe
- `twinopsctl mqtt topics` catalog helper
- Live `GET /api/scene/report` + `GET /api/mqtt/topics` (+ example catalog JSON)
- Offline scene HTML report (`twinopsctl scene --html`)
- Bash completion (`eval "$(twinopsctl completion bash)"`)
- `.editorconfig`
- CI uploads sample drift SARIF artifact; web links to Swagger/OpenAPI
- `twinopsctl openapi` offline schema dump
- Drift SARIF export (`drift-report.sarif`, `--sarif`, ADR-0005)
- Optional pre-commit config (ruff + basic hooks)
- Helm chart README under `deploy/helm/twinops-operator/`
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
