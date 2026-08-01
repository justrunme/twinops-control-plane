# ADR-0020: Real Kit GPU encoder path (single session)

## Status

Accepted (lab / reference) — TwinOps **v1.1**

## Context

ADR-0019 shipped a single-session streaming sidecar with mock frames and
lab-echo SDP. v1.1 must prove one vertical slice without NVCF:

Browser ↔ WebRTC ↔ sidecar ↔ Kit frame drop / mock ↔ software or NVENC host.

## Decision

1. Keep **one session / one GPU index / one browser client**.
2. Add encoder probe: `auto | mock | software | nvenc`.
   - `nvenc` requires host `ffmpeg` with `h264_nvenc` + `nvidia-smi`.
   - Real PeerConnection requires optional extra `twinops[streaming]` (`aiortc`, `av`).
3. Without `aiortc`, signaling stays **lab-echo** so GPU-free CI/demo still works.
4. Frame sources: `mock` (CI), `kit` (process supervisor), `kit-file` (JPEG/PNG/PPM
   drop directory via `TWINOPS_KIT_FRAME_DIR`).
5. Input: `POST /v1/sessions/{id}/input` and WebRTC datachannel messages mirrored
   optionally to JSONL (`TWINOPS_KIT_INPUT_MIRROR`) for Kit extensions.
6. Expose stream quality stats: `startupTimeMs`, `fps`, `bitrateKbps`, `disconnects`
   on session status and Prometheus `/metrics`.
7. Explicit non-goals remain: NVCF, multi-GPU, TURN cluster, multi-tenant.

## Consequences

- Honest dual path: lab-echo without streaming extras; real video track with them
- NVENC is a **host capability**, not a cloud product claim
- Kit integration is file-drop + input mirror — not a proprietary Omniverse SDK
- Opens a clear ops doc for GPU/driver compatibility

## References

- [ADR-0014](0014-lab-webrtc-streaming.md)
- [ADR-0019](0019-kit-streaming-sidecar.md)
- [docs/streaming-sidecar.md](../streaming-sidecar.md)
- [docs/gpu-streaming.md](../gpu-streaming.md)
