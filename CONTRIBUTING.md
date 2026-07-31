# Contributing

Thanks for hacking on TwinOps. Keep changes small, honest, and demoable without a GPU unless the PR is explicitly about Omniverse streaming.

## Local gate

```bash
make install
make doctor
make verify-all
# optional Mosquitto path:
bash scripts/verify_all.sh --with-mqtt
```

Optional git hooks:

```bash
pip install pre-commit
pre-commit install
```

Optional bash completion:

```bash
eval "$(twinopsctl completion bash)"
```

Optional containerized live stack (unauthenticated; local only):

```bash
make docker-live-up
make wait-ready
make live-spike
make scene-live
make live-reconcile
make docker-live-down
```

With a local `make serve` / `make live-demo`, `make scene-live` writes
`/tmp/twinops-scene.json` and `/tmp/twinops-scene.html`.

## Suggested PR slices

1. Compiler / drift / tests  
2. Live API / web UI  
3. Operator / Helm / CRD  
4. Docs / ADRs  

Avoid bundling unrelated refactors with feature work.

## Honesty rules

- Do not claim production / enterprise readiness.
- Do not hard-code a commercial PLM product.
- Mark mock Kit streaming / anonymous MQTT as demo-only.
- Prefer ADRs for architectural choices (`docs/adr/`).

## CLI JSON contract

When a command supports `--json`, stdout must be **JSON only** (no tables /
“Wrote …” lines mixed in). Human summaries stay on the default (non-`--json`)
path. This keeps `live-demo-smoke` and other scripts parseable. Covered
commands include `build`, `drift`, `scene`, `reconcile`, `plm`, and `doctor`.

## Useful docs

Full index: [docs/README.md](docs/README.md).

| Topic | Doc |
| --- | --- |
| Live API | [docs/live-telemetry.md](docs/live-telemetry.md) |
| Operator | [docs/operator.md](docs/operator.md) |
| MQTT | [docs/live-telemetry.md](docs/live-telemetry.md) + ADR-0004 |
| Omniverse highlight | [docs/omniverse.md](docs/omniverse.md) + ADR-0003 |
| PLM mock | [docs/plm-adapter.md](docs/plm-adapter.md) |
| Security | [SECURITY.md](SECURITY.md) / [docs/security.md](docs/security.md) |
