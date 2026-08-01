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
3. Media paths:
   - **lab-echo** without `aiortc`
   - **webrtc-software** via aiortc `VideoStreamTrack`
   - **webrtc-nvenc** via host `ffmpeg -c:v h264_nvenc` → MPEG-TS UDP → aiortc `MediaPlayer`
4. Frame sources: `mock`, `kit`, `kit-file` (`TWINOPS_KIT_FRAME_DIR`).
5. Input: REST `/input` + datachannel → optional JSONL mirror.
6. Expose `encoderInUse`, `mediaPath`, startup/FPS/bitrate/disconnect metrics.
7. Non-goals: NVCF, multi-GPU, TURN cluster, multi-tenant.

## Consequences

- Software path is CI-testable; NVENC path is host-proven via ffmpeg bridge
- Kit integration remains file-drop + input mirror (no proprietary SDK)
- Status/metrics report the encoder actually in use (`h264_nvenc` vs `software`)

## References

- [ADR-0014](0014-lab-webrtc-streaming.md)
- [ADR-0019](0019-kit-streaming-sidecar.md)
- [docs/streaming-sidecar.md](../streaming-sidecar.md)
- [docs/gpu-streaming.md](../gpu-streaming.md)
