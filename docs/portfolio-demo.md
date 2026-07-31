# Portfolio end-to-end demo (v0.10)

One command that proves Kit contract, incident replay, PLM adapters, GitOps
apply/verify, and SQLite persistence form a single product loop.

```bash
make install
make portfolio-demo
```

Artifacts land in `${ARTIFACTS:-/tmp/twinops-portfolio-demo}/out`:

| File | Meaning |
|------|---------|
| `plm-catalog.json` | File PLM adapter snapshot |
| `scene.json` / `scene.html` | Highlight contract after spike |
| `highlight-overlay.usda` | Session-layer overlay (GPU-free Kit path) |
| `incident.json` | Recorded TwinIncident from live timeline |
| `reconcile.json` | Live reconciliation → SYNCED |
| `apply-verify.json` | Local GitOps apply `--verify` |
| `replay-verify.json` | Offline `incident replay --verify` |
| `twinops.sqlite` | Persisted timeline / proposal / audit |
| `drift-report.sarif` | SARIF export when stage is available |

## Chain

```text
PLM desired revision
→ DigitalTwin composition (live bootstrap)
→ heat spike → CRITICAL drift
→ Kit highlight contract / overlay
→ incident recording
→ reconciliation proposal
→ Git-backed apply --verify
→ SYNCED
→ incident replay --verify
→ SQLite restart persistence check
```

## Related

- [ADR-0018](adr/0018-productization-e2e.md)
- [plm-adapters.md](plm-adapters.md)
- [demo-script.md](demo-script.md) — human walkthrough for video after v0.10
