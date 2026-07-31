# TwinOps 5–7 minute demo script

Recorded walkthrough checklist for interviews / demos.

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

One command:

```bash
make demo-gitops
```

Or step-by-step:

```bash
make build drift
twinopsctl reconcile \
  --desired examples/assembly-line/desired.yaml \
  --stage examples/assembly-line/generated/root.usda \
  --observed examples/assembly-line/telemetry.json \
  --manifest examples/assembly-line/twin.yaml \
  --out /tmp/twinops-proposal
twinopsctl apply /tmp/twinops-proposal --no-commit --json
# close the loop (rebuild + re-drift):
twinopsctl apply /tmp/twinops-proposal --no-commit --verify \
  --manifest examples/assembly-line/twin.yaml \
  --desired examples/assembly-line/desired.yaml \
  --observed examples/assembly-line/telemetry.json \
  --json
# or from a running live API after reconcile:
# twinopsctl apply --from-url http://127.0.0.1:8080 --no-commit --print-pr --json
```

## Talking points

- Experimental reference architecture, not a product claim
- Highlight protocol works without Omniverse/GPU
- Live API token via `TWINOPS_API_TOKEN` before any shared bind
- Operator can resolve the token from `liveAPITokenSecretRef` (not plaintext CR)
- MQTT ACL / TLS compose profiles are lab stubs — not production PKI

## Recording tips

1. Start with `make docker-live-up` already warm (UI open).
2. Keep terminal font large; use `make demo-gitops` for the offline GitOps close.
3. Say the non-goals out loud: no enterprise PLM SDK, no forced GPU, no remote PR automation.
4. End on GitHub release tag + portfolio blurb (v1.0.0 tag).
