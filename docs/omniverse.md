# Omniverse as an optional TwinOps runtime

TwinOps is a **GitOps control plane for digital twins**. Omniverse Kit is one
optional way to visualize and execute OpenUSD — not a hard dependency.

CPU-first path (no GPU): compose → drift → live API → highlight contract → web UI.

## Highlight protocol (`twinops.highlight.v1`)

Schema: [`schemas/twinops.highlight.v1.json`](../schemas/twinops.highlight.v1.json).

```bash
make serve
make scene-live
```

Consumers:

1. Poll `GET /api/scene` or `/ws/events` scene frames
2. Optionally `GET /api/streaming/session` (mock / lab WebRTC)
3. Apply highlights for `highlight.enabled` prims
4. Clear when status returns to `SYNCED`

## Kit scene runtime (v0.7)

```text
extensions/twinops_highlight/
```

| Backend | When | Behavior |
| --- | --- | --- |
| `plan` | CI / default CLI | Print highlight plan |
| `overlay` | No Kit | Write highlight USDA overlay |
| `kit` | Inside Omniverse | `displayColor` + selection via `omni.usd` |

Laptop (no GPU):

```bash
make serve
# after a spike:
python extensions/twinops_highlight/twinops_highlight/client.py \
  --base-url http://127.0.0.1:8080 --apply overlay \
  --overlay-out /tmp/twinops-highlight-overlay.usda
```

Inside Kit:

1. Add `extensions/twinops_highlight` to the Kit extension search path
2. Enable **TwinOps Scene Runtime**
3. Set `TWINOPS_API_URL` (and optional `TWINOPS_API_TOKEN`)
4. Open the assembly-line stage — drifted prims highlight on the poll loop

See [ADR-0015](adr/0015-kit-scene-runtime.md).

## Streaming

| Layer | Status |
| --- | --- |
| Lab WebRTC + signaling | ✅ (`serve --webrtc`) |
| Kit App Streaming GPU → browser | ⏳ sidecar after Kit runtime |
| NVCF | ❌ out of scope |

## Honest status

- ✅ Highlight API + web inspector + lab WebRTC
- ✅ Kit extension runtime loop + apply backends
- ✅ Session-layer highlights (source assets untouched; reconnect/idempotent)
- ⏳ Kit App Streaming browser session with RTX frames
- ❌ NVCF / cloud GPU product claims
