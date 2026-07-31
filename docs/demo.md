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
docker run --rm -p 8080:8080 twinops-live:0.3.2
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

```bash
curl -s http://127.0.0.1:8080/api/health
curl -s -X POST http://127.0.0.1:8080/api/simulate/spike | jq '.drift.status.summary'
curl -s -X POST http://127.0.0.1:8080/api/reconcile | jq '{changes, hasDrift: .drift.status.hasDrift}'
```

Example output:

```text
spike:      { "CRITICAL": 1, "DRIFT": 5, ... }
reconcile:  { "changes": 4, "hasDrift": false }
```
