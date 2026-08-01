# GPU streaming compatibility (v1.1)

Single GPU · single Kit session · no NVCF. This page documents what the sidecar
expects from the **host**, not a cloud fleet.

## Encoder selection

| `TWINOPS_SIDECAR_ENCODER` / `--encoder` | Behavior |
| --- | --- |
| `auto` (default) | Prefer `nvenc` if ffmpeg reports `h264_nvenc` + `nvidia-smi`; else `software` if `aiortc` installed; else `mock` |
| `nvenc` | Require NVENC; fall back to `software` with a note if missing |
| `software` | aiortc software encode path |
| `mock` | Force lab-echo SDP (GPU-free CI) |

Real WebRTC **media** also needs:

```bash
pip install -e '.[live,streaming]'
# or: pip install 'twinops[streaming]'
```

Without `aiortc`/`av`, the API still works and answers with **lab-echo** SDP so
demos and CI stay green on CPU-only hosts.

## Host prerequisites (NVENC path)

| Component | Why |
| --- | --- |
| NVIDIA GPU + driver | `nvidia-smi` must succeed for the configured `TWINOPS_GPU_INDEX` |
| CUDA-capable driver matching Kit/App Streaming needs | Kit owns RTX render; sidecar does not vendor a driver matrix |
| `ffmpeg` with `h264_nvenc` | Capability probe (`ffmpeg -encoders \| grep h264_nvenc`) |
| Python `twinops[streaming]` | aiortc PeerConnection + video track |
| Kit (or helper) writing frames | `--frame-source kit-file` + `TWINOPS_KIT_FRAME_DIR` |

Validated locally when present; CI does **not** require a GPU.

### Suggested driver posture

- Use the driver branch recommended by your Omniverse / Kit release notes.
- Confirm `nvidia-smi` and `ffmpeg -encoders | grep h264_nvenc` on the same host
  that runs the sidecar (same GPU index).
- Do not run multiple Kit sessions against one sidecar instance.

## Frame + input contract

```text
Kit / helper  --JPEG/PNG/PPM-->  TWINOPS_KIT_FRAME_DIR
Browser input --REST/datachannel--> sidecar --JSONL--> TWINOPS_KIT_INPUT_MIRROR
```

Supported input types: `mousemove`, `mousedown`, `mouseup`, `keydown`, `keyup`, `wheel`.

Datachannel name hint: `twinops-input` (JSON payloads, same schema as REST).

## Metrics

Prometheus (`GET /metrics`) and `/v1/status` expose:

- `startupTimeMs` — offer answered → media ready
- `fps` / `bitrateKbps` — estimated from emitted frames
- `disconnects` — peer connection lost/failed
- GPU gauges via `nvidia-smi` when available

## Explicit non-goals

NVCF, multi-user, multi-GPU, TURN clusters, autoscaling, multi-region.

See [ADR-0020](adr/0020-kit-gpu-encoder-path.md) and [streaming-sidecar.md](streaming-sidecar.md).
