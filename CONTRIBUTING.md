# Contributing

Thanks for hacking on TwinOps. Keep changes small, honest, and demoable without a GPU unless the PR is explicitly about Omniverse streaming.

## Development setup

```bash
make install
make doctor
```

Optional git hooks:

```bash
pip install pre-commit
pre-commit install
```

## Branch naming

Use conventional prefixes:

- `feat/<short-name>` — new capability
- `fix/<short-name>` — bug fix
- `chore/<short-name>` — maintenance
- `docs/<short-name>` — documentation only
- `ci/<short-name>` — workflow / tooling

## Commits

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:`, `ci:`.

## Tests

```bash
make verify-all
# optional Mosquitto path:
bash scripts/verify_all.sh --with-mqtt
# Go packages:
make go-test
```

Useful slices: `make test`, `make lint`, `make live-demo-smoke`.

## Pull requests

Open against `main`. CI must be green. Prefer squash merge.

Checklist:

- [ ] `make verify-all` (or the relevant subset) passes locally
- [ ] Branch name uses `feat/` / `fix/` / `chore/` / `docs/` / `ci/`
- [ ] Commits follow Conventional Commits
- [ ] Docs / examples updated when behavior changes
- [ ] No unrelated refactors bundled with the feature

## Honesty rules

- Do not claim production / enterprise readiness.
- Do not hard-code a commercial PLM product.
- Mark mock Kit streaming / anonymous MQTT as demo-only.
- Prefer ADRs for architectural choices (`docs/adr/`).

## Useful docs

Full index: [docs/README.md](docs/README.md).
