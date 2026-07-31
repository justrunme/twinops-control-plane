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
