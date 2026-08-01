# TwinOps 1.1.0 — Kit GPU encoder path

Theme release after the 1.0 stable reference architecture.

## What shipped

- Encoder probe: `auto | mock | software | nvenc` (host ffmpeg `h264_nvenc`)
- Optional `twinops[streaming]` → real aiortc video track (not browser canvas lab-echo)
- Frame sources: `mock`, `kit`, `kit-file` drop directory
- Input bridge: REST `/input` + datachannel → optional JSONL for Kit
- Metrics: startup time, FPS, bitrate, disconnects (+ GPU gauges)
- GPU-free fallback unchanged when streaming extras are absent

## Verify

```bash
make install
make test
make streaming-sidecar-smoke
# optional real media deps:
# pip install -e '.[streaming]'
```

## Docs

- [streaming-sidecar.md](streaming-sidecar.md)
- [gpu-streaming.md](gpu-streaming.md)
- [ADR-0020](adr/0020-kit-gpu-encoder-path.md)

## Non-goals (still)

NVCF, multi-user, multi-GPU, TURN cluster, autoscaling.
