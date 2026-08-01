# GPU streaming (post-1.2 honesty)

Single GPU · single Kit session · no NVCF.

## Honest encoder fields

| Field | Meaning |
| --- | --- |
| `ingestEncoder` | How pixels enter the sidecar (`none` / `software` / `h264_nvenc`) |
| `webrtcEncoder` | What produces WebRTC RTP (`none` / `aiortc`) |
| `mediaPath` | `lab-echo` · `webrtc-software` · `nvenc-mpegts-aiortc` |
| `encoderInUse` | Deprecated alias — do **not** treat as the RTP codec |

### NVENC path today

```text
kit-file / testsrc
   → ffmpeg h264_nvenc
   → MPEG-TS (UDP)
   → aiortc MediaPlayer (decode)
   → aiortc re-encodes RTP
```

So NVENC is a real **ingest** GPU encode, not the final WebRTC encoder.
Kit-file drops are watched; ffmpeg restarts when a newer JPEG/PNG appears.

## Smokes

```bash
make streaming-sidecar-smoke          # mock / lab-echo (CI)
bash scripts/streaming_nvenc_smoke.sh # skips if no NVENC; else offer+track.recv()
```

Manual self-hosted workflow: [`.github/workflows/gpu-validate.yml`](../.github/workflows/gpu-validate.yml)
(runs the NVENC smoke, not mock).

## Non-goals

NVCF, multi-user, multi-GPU, TURN, end-to-end NVENC RTP (passthrough / webrtcbin).
