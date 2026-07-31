# TwinOps 5–7 minute demo script

Recorded walkthrough checklist for portfolio / interviews.

## Setup (30s)

```bash
make docker-live-up   # or: make live-demo
# UI: http://127.0.0.1:8080/
```

## Storyboard

1. **Brand the problem (30s)** — PLM desired vs rendered USD vs live telemetry drift.
2. **Show calm twin (45s)** — UI timeline SYNCED; scene inspector quiet; Kit mock viewport calm.
3. **Spike (45s)** — press `1` or `twinopsctl live spike`; drift + red highlights appear.
4. **Scene contract (45s)** — open `/api/scene` / scene HTML; mention `twinops.highlight.v1` (GPU-free).
5. **Reconcile (45s)** — press `2` or `twinopsctl live reconcile`; timeline returns to SYNCED.
6. **GitOps apply (60s)** — offline: `twinopsctl reconcile …` then `twinopsctl apply <dir>` on a branch (no push).
7. **Close (30s)** — operator CR + MQTT catalog + optional token auth; explicit non-goals.

## Offline GitOps path

```bash
make build drift
twinopsctl reconcile \
  --desired examples/assembly-line/desired.yaml \
  --stage examples/assembly-line/generated/root.usda \
  --observed examples/assembly-line/telemetry.json \
  --manifest examples/assembly-line/twin.yaml \
  --out /tmp/twinops-proposal
twinopsctl apply /tmp/twinops-proposal --no-commit --json
# or from a running live API after reconcile:
# twinopsctl apply --from-url http://127.0.0.1:8080 --no-commit --json
```

## Talking points

- Experimental reference architecture, not a product claim
- Highlight protocol works without Omniverse/GPU
- Live API token via `TWINOPS_API_TOKEN` before any shared bind
