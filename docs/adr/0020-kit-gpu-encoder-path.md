# ADR-0020: Real Kit GPU encoder path (single session)

## Status

Accepted (lab / reference) — TwinOps **v1.1**

## Context

ADR-0019 shipped a single-session streaming sidecar with mock frames and
lab-echo SDP. v1.1 must prove one vertical slice without NVCF:

Browser ↔ WebRTC ↔ sidecar ↔ Kit frame drop / mock ↔ software or NVENC host.

## Decision

1. Keep **one session / one GPU index / one browser client**.
2. Encoder probe: `auto | mock | software | nvenc`.
3. Media paths (honest):
   - **lab-echo** without `aiortc`
   - **webrtc-software** — ingest=`software`, webrtc=`aiortc`
   - **nvenc-mpegts-aiortc** — ingest=`h264_nvenc` (ffmpeg), webrtc=`aiortc` (re-encode)
4. Frame sources: `mock`, `kit`, `kit-file` (watched; ffmpeg restarts on newer stills).
5. Input: REST `/input` + datachannel → optional JSONL mirror.
6. Expose `ingestEncoder` / `webrtcEncoder` / `mediaPath` (+ deprecated `encoderInUse`).
7. Non-goals: NVCF, multi-GPU, TURN, end-to-end NVENC RTP passthrough.

## Consequences

- Claims match the pipeline: NVENC is an ingest bridge until passthrough lands
- Software path is CI-testable with `track.recv()`; NVENC has a dedicated smoke

## References

- [ADR-0014](0014-lab-webrtc-streaming.md)
- [ADR-0019](0019-kit-streaming-sidecar.md)
- [docs/streaming-sidecar.md](../streaming-sidecar.md)
- [docs/gpu-streaming.md](../gpu-streaming.md)
