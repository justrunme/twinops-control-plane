# GPU streaming (v1.2)

Single GPU · single Kit session · no NVCF.

## Paths

| Path | When | What happens |
| --- | --- | --- |
| `lab-echo` | no `twinops[streaming]` or `--encoder mock` | SDP echo; browser keeps local MediaStream (CI default) |
| `webrtc-software` | `aiortc` installed, NVENC absent or forced software | Real WebRTC video track from mock/kit-file frames |
| `webrtc-nvenc` | `ffmpeg` has `h264_nvenc` + `nvidia-smi` | ffmpeg encodes on GPU → MPEG-TS UDP → aiortc `MediaPlayer` |

Status exposes `encoderInUse` (`none` / `software` / `h264_nvenc`) and `mediaPath`.

## Host prerequisites (NVENC)

| Component | Check |
| --- | --- |
| NVIDIA driver | `nvidia-smi` |
| ffmpeg NVENC | `ffmpeg -encoders \| grep h264_nvenc` |
| Python extras | `pip install -e '.[live,streaming]'` |
| Kit frames (optional) | JPEG/PNG in `TWINOPS_KIT_FRAME_DIR` |

Manual validation workflow (self-hosted GPU runner):
[`.github/workflows/gpu-validate.yml`](../.github/workflows/gpu-validate.yml).

## Input

`POST /v1/sessions/{id}/input` or datachannel `twinops-input` → optional JSONL mirror.

## Non-goals

NVCF, multi-user, multi-GPU, TURN clusters, autoscaling.

See [ADR-0020](adr/0020-kit-gpu-encoder-path.md) and [streaming-sidecar.md](streaming-sidecar.md).
