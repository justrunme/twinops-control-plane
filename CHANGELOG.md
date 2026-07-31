# Changelog

All notable TwinOps changes are listed here. Dates are UTC.

## Unreleased

## 0.6.0 — 2026-07-31

- Lab WebRTC: `serve --webrtc`, signaling API, browser MediaStream UI (ADR-0014)
- HTTPS + mTLS for live API (`--tls-*`, `scripts/gen_live_tls_certs.sh`)
- Demo SSO JWT (`TWINOPS_SSO_JWT_SECRET`, `twinopsctl sso issue`) + oauth2-proxy compose stub (ADR-0013)

## 0.5.9 — 2026-07-31

- Kit streaming session mock exposes `spec.webrtc` placeholder (ADR-0012)
- Docs: mock → future Kit App Streaming / WebRTC contract

## 0.5.8 — 2026-07-31

- `make mqtt-tls-smoke` / `scripts/mqtt_tls_smoke.sh` end-to-end lab TLS pub/sub

## 0.5.7 — 2026-07-31

- `twinopsctl serve --mqtt-tls` / `--mqtt-ca` / `--mqtt-tls-insecure` for lab TLS brokers
- MQTT endpoint status exposes `tls` flag

## 0.5.6 — 2026-07-31

- GitHub Actions publish workflow for `twinops-live` / `twinops-operator` to GHCR on `v*` tags
- `docs/images.md` pull/build notes

## 0.5.5 — 2026-07-31

- Helm umbrella `Chart.lock` + `make helm-deps` / `make helm-template`
- Doctor check for Chart.lock; charts/ packages gitignored

## 0.5.4 — 2026-07-31

- Operator `spec.liveAPITokenSecretRef` (Secret-backed live API token)
- RBAC: controller can get/list/watch Secrets for token resolve

## 0.5.3 — 2026-07-31

- `make demo-gitops` / `scripts/demo_gitops.sh` offline apply+verify walkthrough
- `twinopsctl apply --no-branch` copies artifacts without switching git branches
- Lab MQTT TLS compose stub (`:8883`, self-signed certs gitignored)
- Helm umbrella live API token via Secret (`twinops-live-api`)
- Doctor checks for MQTT TLS profile + demo-gitops script
- Roadmap Next focus updated (0.5.x → 0.6)

## 0.5.2 — 2026-07-31

- `twinopsctl doctor` checks MQTT ACL profile + Helm umbrella presence

## 0.5.1 — 2026-07-31

- Helm umbrella optional twinops-live Deployment/Service stub
- Demo script documents apply --verify close-out
- ADR-0010 apply verification loop

## 0.5.0 — 2026-07-31

- `twinopsctl apply --verify` rebuilds stage with overlay and re-runs drift
- Mosquitto ACL demo compose profile (password file, lab-only)
- Helm umbrella chart skeleton (`deploy/helm/twinops`)
- Kit highlight client `--ws` for /ws/events scene frames
- Roadmap Next focus (0.5.x) + Milestone 9 status corrected
- Docker image tags aligned to current release line

## 0.4.9 — 2026-07-31

- DigitalTwin kubectl printcolumn for status.live.ready

## 0.4.8 — 2026-07-31

- Helm optional sampleTwin CR with liveAPIURL wiring

## 0.4.7 — 2026-07-31

- Kit highlight client: `--session` / `--watch` / `--token`

## 0.4.6 — 2026-07-31

- Web UI passes `VITE_TWINOPS_API_TOKEN`; WS accepts `?token=` for demos

## 0.4.5 — 2026-07-31

- Prometheus Operator ServiceMonitor stub for twinops-live
- Sequence diagrams for live apply + operator live probe

## 0.4.4 — 2026-07-31

- Optional MQTT ingest schema gate via `TWINOPS_MQTT_STRICT_SCHEMA`
- README clarifies TwinOps vs Grafana+USD dashboards

## 0.4.3 — 2026-07-31

- `twinopsctl apply --print-pr` suggests a manual gh pr create command
- Prometheus scrape snippet + `make apply-live`

## 0.4.2 — 2026-07-31

- `GET /api/proposal/latest/bundle` + `twinopsctl apply --from-url`
- ADR-0009 MQTT payload schema + observability scrape notes

## 0.4.1 — 2026-07-31

- `twinopsctl mqtt validate` for `twinops.mqtt.payload.v1` JSON files
- MQTT payload validator helpers + example payload
- Teamcenter/Windchill PLM stub adapters (NotImplemented surface)
- CRD/sample fields for `spec.liveAPIURL` / `status.live`

## 0.4.0 — 2026-07-31

- Milestone 0.4 foundations: local GitOps apply, live API token auth, operator live status sync
- `twinopsctl apply` copies proposal artifacts onto a local branch (no push)
- Optional `TWINOPS_API_TOKEN` / `--api-token` for live API + CLI live helpers
- `GET /api/streaming/session` mock Kit streaming descriptor
- Operator `spec.liveAPIURL` probes live ready/metrics into `status.live`
- `PlmAdapter` protocol + MQTT payload schema `twinops.mqtt.payload.v1`
- Grafana overview dashboard stub + Helm umbrella notes
- ADR-0007/0008 + demo script for portfolio walkthroughs
- `twinopsctl completion zsh` (from 0.3.10)

## 0.3.10 — 2026-07-31

- `twinopsctl completion zsh` shell completion script

## 0.3.9 — 2026-07-31

- `twinopsctl doctor --json` emits JSON-only stdout
- `twinopsctl reconcile --json` emits JSON-only stdout

## 0.3.8 — 2026-07-31

- CONTRIBUTING documents the CLI `--json` stdout contract
- `twinopsctl build --json` emits JSON-only stdout

## 0.3.7 — 2026-07-31

- `twinopsctl plm show|compare --json` emits JSON-only stdout
- `twinopsctl drift --json` emits JSON-only stdout for scripts

## 0.3.6 — 2026-07-31

- CONTRIBUTING documents `scene-live` in the docker-live path
- `.gitattributes` + CODEOWNERS for schemas/scene/telemetry
- Docs mention `/tmp` artifacts from `make scene-live`
- `make scene-live` also writes /tmp scene JSON + HTML
- README documents `scene-live` / `live-status` DX path

## 0.3.5 — 2026-07-31

- `twinopsctl scene --json` emits JSON-only stdout for scripts
- Live-demo smoke tolerates scene CLI drift exit code after spike
- Live-demo smoke fetches scene via `twinopsctl scene --from-url --strict`
- Makefile help lists `scene-live`
- `make scene-live` + docs for `scene --from-url`
- `twinopsctl scene --from-url` fetch/validate live highlight snapshots

## 0.3.4 — 2026-07-31

- Live demo / docs use `twinopsctl live status`
- `twinopsctl live status` / `make live-status`
- `make mqtt-topics-check` + web link to `/api/ready`
- `twinopsctl doctor` checks MQTT topic catalog sync
- `RELEASING.md` checklist
- Live API asserts highlight schema on every `/api/scene` snapshot
- Live-demo smoke validates `/api/scene` against twinops.highlight.v1
- `scripts/wait_ready.sh` / `make wait-ready` for compose/demo boots
- CONTRIBUTING notes for `docker-live-up`

## 0.3.3 — 2026-07-31

- Architecture docs refresh for delivered live API / MQTT / highlight surface
- Web UI shows twinopsctl/API version from `/api/health`
- README release badge; live-demo uses `twinopsctl ready`
- `twinopsctl ready` / `make ready`
- Compose live stack (`deploy/demo/docker-compose.live.yml`) + `make live-spike|live-reconcile`
- `twinopsctl metrics` / `make metrics`
- Live demo smoke uses `twinopsctl live spike|reconcile`
- `twinopsctl live spike|reconcile` against a running live API

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
