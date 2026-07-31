# TwinOps demo guide

## 2-minute live demo (recommended)

```bash
make install
make live-demo
```

Opens the control plane at [http://127.0.0.1:8080/](http://127.0.0.1:8080/).

Keyboard shortcuts in the UI: **1** = heat spike, **2** = reconcile.

Optional containerized live API (demo only, unauthenticated):

```bash
make docker-live
docker run --rm -p 8080:8080 twinops-live:0.3.8
# or Mosquitto + live API/UI:
make docker-live-up
make wait-ready
```

What you will see:

```text
1. Trigger heat spike
      ↓
   CRITICAL temperature + firmware/PLM drift
      ↓
2. Apply reconciliation
      ↓
   USD overlay applied + line healed
      ↓
3. Twin returns to SYNCED
```

Smoke-only (CI / quick verify, no browser):

```bash
make live-demo-smoke
```

## Offline CLI demo (no server)

```bash
make demo
```

Produces:

- composed USDA stage
- drift HTML report
- reconciliation proposal (`PULL_REQUEST.md`)

## Expected API storyboard

With `make serve` (or `make live-demo`) already running:

```bash
make live-status
make live-spike
make scene-live   # also writes /tmp/twinops-scene.{json,html}
make timeline
make live-reconcile
make proposal
```

Equivalent CLI:

```bash
twinopsctl live status
twinopsctl live spike --json
twinopsctl live reconcile --json
twinopsctl proposal
```

Example output:

```text
spike:      hasDrift=True summary={'CRITICAL': 1, ...}
reconcile:  changes=4 hasDrift=False
```
