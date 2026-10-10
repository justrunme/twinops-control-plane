# Results

Measured from CI run [`38066458460`](https://github.com/justrunme/twinops-control-plane/actions/runs/38066458460) (branch `main`, job **Python 3.12**, 2026-10-10).

Artifacts: [`e2e-demo-py3.12`](https://github.com/justrunme/twinops-control-plane/actions/runs/38066458460) (incident, reconcile, replay-verify, timeline).

## End-to-end demo flow

| Step | Outcome | Notes |
| --- | --- | --- |
| MQTT heat spike | CRITICAL drift | `hasDrift=true`, summary `CRITICAL=1, DRIFT=5, SYNCED=6` |
| Scene highlight | Robot01 CRITICAL | Kit highlight contract (`scene.v1`) validated |
| Reconcile / apply | SYNCED | `changes=3`, summary `SYNCED=9` |
| Incident replay `--verify` | verified | `stepsPlayed=6`, `verified=true` |
| SQLite persistence restart | OK | `persisted timeline events=5` |

## Timings (wall clock from job log)

| Metric | Value | Source |
| --- | --- | --- |
| Smoke: spike → reconcile → SYNCED | 0.43 s | log timestamps 16:11:40.058–16:11:40.490Z |
| E2E after API healthy: spike → replay → persistence | 1.90 s | log timestamps 16:11:41.330–16:11:43.228Z |

Full scenario script: [`scripts/e2e_demo.sh`](../scripts/e2e_demo.sh).
