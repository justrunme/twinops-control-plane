# Kit streaming sidecar (v0.11)

Single-session process between TwinOps API and Kit/mock frames:

```text
┌─────────────────────┐
│ TwinOps API         │  signaling pointer / scene contract
└──────────┬──────────┘
           │ TWINOPS_STREAMING_SIDECAR_URL
┌──────────▼──────────┐
│ Streaming sidecar   │  session · health · idle · metrics
└──────────┬──────────┘
           │ frames / Kit process
┌──────────▼──────────┐
│ Mock frames (CI) or │
│ Omniverse Kit App   │
└─────────────────────┘
```

## Quick start

```bash
# terminal 1
twinopsctl streaming-sidecar --port 8091

# terminal 2
twinopsctl serve --example examples/assembly-line \
  --streaming-sidecar http://127.0.0.1:8091 --webrtc

# smoke
make streaming-sidecar-smoke
```

Docker (mock frames):

```bash
docker compose -f deploy/demo/docker-compose.streaming.yml up --build
```

## API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | liveness |
| GET | `/ready` | readiness |
| GET | `/v1/status` | session + GPU + limitations |
| POST | `/v1/sessions` | create (409 if one already active) |
| GET | `/v1/sessions/{id}` | get |
| DELETE | `/v1/sessions/{id}` | delete |
| POST | `/v1/sessions/{id}/signal` | offer / candidate / get |
| POST | `/v1/sessions/{id}/frame` | emit mock/Kit tick |
| GET | `/metrics` | Prometheus |

## Limitations (intentional)

- One session, one GPU index, one browser client
- No TURN cluster, autoscaling, multi-region, or NVCF
- Default frames are **synthetic** (`--frame-source mock`)
- `--frame-source kit` only supervises `TWINOPS_KIT_COMMAND` — RTX/NVENC
  encoder not wired yet; WebRTC answer is lab-echo
- DCGM optional; `nvidia-smi` used when present

See [ADR-0019](adr/0019-kit-streaming-sidecar.md).
