# Upgrade notes

## 0.10.x → 0.11.x

- Command rename: `make portfolio-demo` → **`make e2e-demo`**
  (script: `scripts/e2e_demo.sh`, artifacts: `/tmp/twinops-e2e-demo`)
- New optional process: `twinopsctl streaming-sidecar`
- Live API mode `kit-sidecar` when `TWINOPS_STREAMING_SIDECAR_URL` is set
- No SQLite schema break from 0.10 → 0.11

## 0.11.x → 1.0.0

- Positioning: **stable reference architecture** (still not a production industrial platform)
- New docs: backup/restore, compatibility matrix, ops checklist
- CLI: `twinopsctl state backup|restore` for SQLite
- SQLite files from 0.10/0.11 remain readable (same schema)
- Streaming sidecar still uses mock frames by default; NVENC encoder remains a follow-up

## Recommended upgrade path

```bash
git fetch --tags
git checkout v1.0.0
make install
make verify-all          # local; heavy — use before cutting releases
# or lighter:
make test && make e2e-demo && make streaming-sidecar-smoke
```

If you keep a persistent DB across upgrades:

```bash
twinopsctl state backup --db "$DB" --out /tmp/pre-1.0.sqlite
# upgrade package
twinopsctl state restore --db "$DB" --from /tmp/pre-1.0.sqlite
```

## Breaking / renamed surfaces

| Old | New |
|-----|-----|
| `make portfolio-demo` | `make e2e-demo` |
| `/tmp/twinops-portfolio-demo` | `/tmp/twinops-e2e-demo` |
| docs/portfolio-demo.md | docs/e2e-demo.md |
