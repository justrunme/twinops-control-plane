# Evidence

This document maps product claims to proof status so a reviewer can distinguish
**tested production-like behaviour** from **reference** or **simulated** parts.

Status vocabulary:

| Status | Meaning |
| --- | --- |
| Tested in CI | Exercised on `main` by a named workflow/job with a linkable successful run |
| Reference implementation | Integrated example or adapter path; not a full production adapter suite |
| Simulated | Demo/fixture/synthetic inputs (not live PLM/Omniverse/cloud telemetry) |
| Not yet | No successful CI proof on `main` for this claim |

Numbers below are taken only from repository docs (`docs/results.md` / `docs/results.json`)
and linked GitHub Actions runs. If a metric is not in those sources, status is **Not yet**.

## Claim table

| Claim | Status | Scenario + environment | Real limits | Proof link | Negative tests |
| --- | --- | --- | --- | --- | --- |
| Three-way drift detect → reconcile → SYNCED (MQTT heat spike) | Tested in CI | CI job **Python 3.12**; in-process / API e2e via `scripts/e2e_demo.sh` (not a multi-node cluster) | Wall-clock timings are CI runner local; not industrial plant latency or Omniverse Kit | [CI run 38066458460](https://github.com/justrunme/twinops-control-plane/actions/runs/38066458460) · SHA `081fbe580018e37b05826317d6d799dc0665b3f4` · artifact `e2e-demo-py3.12`; documented in [docs/results.md](results.md) (smoke 0.43 s, e2e 1.90 s) | Drift must clear to SYNCED after reconcile; replay `--verify` must report `verified=true` |
| Incident replay verify + SQLite timeline persistence | Tested in CI | Same run/job as above | SQLite single-process persistence; not HA Postgres | Same run · artifact `e2e-demo-py3.12` · `stepsPlayed=6`, `persisted timeline events=5` | Replay verify fails closed when steps do not match |
| DigitalTwin operator reconcile on kind (artifact / Helm / Job / OCI+S3) | Tested in CI | `helm/kind-action@v1` jobs: Operator artifact E2E, in-cluster Helm E2E, Job-mode E2E, OCI/S3 E2E (+ registry + MinIO) | Single-node kind; MinIO stands in for S3; image load via kind | Latest green CI on main: [38119214119](https://github.com/justrunme/twinops-control-plane/actions/runs/38119214119) · SHA `fba1eb68872f3c32e3f67871ebc163749cff6b51` | Operator jobs fail the workflow on reconcile/assert errors |
| Go operator unit/envtest coverage | Tested in CI | Job **Go operator** on ubuntu runners | envtest ≠ full multi-cluster control plane | Same CI run 38119214119 · artifact `controllers-coverage` | `go test` / envtest failures fail CI |
| OpenUSD compose / pxr validate | Tested in CI | Job **OpenUSD pxr validate** | Validates composition path in CI; not a full Omniverse Kit render farm | Same CI run 38119214119 | Validation failures fail CI |
| Live MQTT publish + ingest smoke | Tested in CI | Job **MQTT publish+ingest smoke** | Smoke only; not long-running industrial MQTT mesh | Same CI run 38119214119 | Smoke assert failures fail CI |
| NVIDIA Omniverse Kit / WebRTC streaming runtime | Reference implementation | Optional runtime docs (`docs/omniverse.md`, `docs/streaming-sidecar.md`, `docs/gpu-streaming.md`); GPU workflow exists separately | Not required for SYNCED control-plane path; Kit treated as optional | GPU validate workflow present; no measured Kit e2e numbers in `docs/results.*` → do not treat as production-proved Kit | N/A (optional path) |
| Production PLM/ERP adapter at scale | Not yet / Reference | Adapter docs and demos (`docs/plm-adapter.md`) | No multi-site PLM soak or vendor certification in CI results | — | — |

## Not proven / out of scope

- Multi-cluster / multi-region digital-twin federation
- Omniverse Kit as a mandatory runtime (explicitly optional)
- Industrial-scale USD scene sizes, GPU streaming SLOs, or plant-floor MQTT volume
- Treating CI wall-clock seconds as contractual plant RTO

## How to reproduce

```bash
make install
make live-demo
make live-demo-smoke
# or the script behind docs/results.md:
bash scripts/e2e_demo.sh
```

Operator kind paths are the `Operator * E2E (kind)` jobs in `.github/workflows/ci.yml`.
