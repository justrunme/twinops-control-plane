# Kit streaming sidecar (v1.1)

Single-session process between TwinOps API and Kit/mock frames with optional
real WebRTC media (software or host NVENC). Not NVCF.

```text
┌─────────────────────┐
│ TwinOps API         │  signaling pointer / scene contract
└──────────┬──────────┘
           │ TWINOPS_STREAMING_SIDECAR_URL
┌──────────▼──────────┐
│ Streaming sidecar   │  session · encoder · input · metrics
└──────────┬──────────┘
           │ frames / Kit process / kit-file drops
┌──────────▼──────────┐
│ Mock | Kit | files  │  → aiortc track (or lab-echo fallback)
└─────────────────────┘
```

## Quick start (GPU-free)

```bash
# terminal 1
twinopsctl streaming-sidecar --port 8091 --encoder mock

# terminal 2
twinopsctl serve --example examples/assembly-line \
  --streaming-sidecar http://127.0.0.1:8091 --webrtc

make streaming-sidecar-smoke
```

## Real media path (one GPU)

```bash
pip install -e '.[live,streaming]'

twinopsctl streaming-sidecar \
  --port 8091 \
  --encoder auto \
  --frame-source kit-file \
  --kit-frame-dir /tmp/twinops-kit-frames \
  --input-mirror /tmp/twinops-kit-input.jsonl
```

Point Kit (or a drop helper) at `/tmp/twinops-kit-frames` with JPEG/PNG/PPM.
Browser mouse/keyboard → `POST /v1/sessions/{id}/input` or datachannel
`twinops-input`. Compatibility notes: [gpu-streaming.md](gpu-streaming.md).

Docker (mock frames / lab-echo by default):

```bash
docker compose -f deploy/demo/docker-compose.streaming.yml up --build
```

## API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | liveness + selected encoder |
| GET | `/ready` | readiness + encoder capability |
| GET | `/v1/status` | session, encoder, input, GPU, limitations |
| POST | `/v1/sessions` | create (409 if one already active) |
| GET | `/v1/sessions/{id}` | get (+ stream stats) |
| DELETE | `/v1/sessions/{id}` | delete / cleanup |
| POST | `/v1/sessions/{id}/signal` | offer / candidate / get |
| POST | `/v1/sessions/{id}/frame` | emit mock/Kit tick |
| POST | `/v1/sessions/{id}/input` | mouse/keyboard → Kit bridge |
| GET | `/metrics` | Prometheus (FPS, bitrate, disconnects, GPU) |

## Environment

| Variable | Default | Notes |
| --- | --- | --- |
| `TWINOPS_SIDECAR_HOST` / `PORT` | `127.0.0.1` / `8091` | bind |
| `TWINOPS_SIDECAR_IDLE_TIMEOUT` | `300` | seconds |
| `TWINOPS_SIDECAR_FRAME_SOURCE` | `mock` | `mock` \| `kit` \| `kit-file` |
| `TWINOPS_SIDECAR_ENCODER` | `auto` | `auto` \| `mock` \| `software` \| `nvenc` |
| `TWINOPS_KIT_COMMAND` | — | required for `kit` |
| `TWINOPS_KIT_FRAME_DIR` | `/tmp/twinops-kit-frames` | for `kit-file` |
| `TWINOPS_KIT_INPUT_MIRROR` | — | JSONL for Kit |
| `TWINOPS_GPU_INDEX` | `0` | nvidia-smi id |

## Limitations (intentional)

- One session, one GPU index, one browser client
- No TURN cluster, autoscaling, multi-region, or NVCF
- Without `twinops[streaming]`, answers are **lab-echo** (GPU-free demo)
- NVENC is host ffmpeg `h264_nvenc`, not a cloud encoder product
- `kit` mode supervises a process; pair with `kit-file` for pixels

See [ADR-0020](adr/0020-kit-gpu-encoder-path.md) and [ADR-0019](adr/0019-kit-streaming-sidecar.md).
