# Omniverse / GPU streaming (Milestone 6 foundation)

TwinOps treats Omniverse as an **optional visualization runtime**, not a hard dependency.
Milestones 1–5 already compose OpenUSD, detect drift, and reconcile without a GPU.

This milestone adds the **highlight contract** that a Kit extension or streaming client
can consume.

## Highlight protocol (`twinops.highlight.v1`)

```bash
make serve
curl -s http://127.0.0.1:8080/api/scene | jq .
```

Payload shape:

```json
{
  "twin": "assembly-line-a",
  "hasDrift": true,
  "prims": [
    {
      "prim": "/World/Factory/LineA/Robot01",
      "status": "CRITICAL",
      "highlight": {
        "enabled": true,
        "color": [0.5, 0.11, 0.11],
        "intensity": 1.0
      },
      "findings": []
    }
  ],
  "protocol": { "name": "twinops.highlight.v1" }
}
```

Consumers should:

1. Poll `GET /api/scene` (or subscribe to future WebSocket scene frames)
2. For each prim with `highlight.enabled`, select / tint / emissive-highlight it
3. Clear highlights when status returns to `SYNCED`

## Kit extension stub

```text
extensions/twinops_highlight/
```

Runnable without Omniverse:

```bash
# terminal 1
make serve

# terminal 2 — after a heat spike
python extensions/twinops_highlight/twinops_highlight/client.py --base-url http://127.0.0.1:8080
```

Inside Kit, enable the extension from this folder and replace `apply_highlights()`
with `omni.kit.commands` / USD selection APIs.

## GPU Operator / Kit App Streaming notes

These are **deployment sketches**, not claimed as implemented:

| Piece | Notes |
| --- | --- |
| NVIDIA GPU Operator | Install via Helm on a GPU node pool; expose MIG/time-slicing as needed |
| Omniverse Kit | Run Kit with the TwinOps highlight extension mounted |
| Kit App Streaming | Session lifecycle + browser client arrive after the highlight loop is solid |
| NVCF | Explicitly out of scope until a real streaming path exists |

Example Helm-style values sketch (not a chart):

```yaml
# deploy notes only — do not treat as production
gpuOperator:
  driver:
    enabled: true
kitStreaming:
  enabled: false
  twinopsApi: http://twinops-live.twinops-system.svc:8080
  extensionPath: /opt/twinops/extensions/twinops_highlight
```

## Honest status

- ✅ Scene highlight API + web inspector
- ✅ Scene snapshots on WebSocket drift/reconcile frames
- ✅ Mock Kit streaming viewport in the web UI (no GPU)
- ✅ Kit extension stub that polls TwinOps without GPU
- ❌ Full Omniverse Kit App Streaming browser session
- ❌ NVCF / cloud GPU product claims
