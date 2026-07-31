# ADR-0019: Single-session Kit streaming sidecar

## Status

Accepted (lab / reference)

## Context

Lab WebRTC (ADR-0014) proves browser MediaStream + signaling without GPU.
v0.11 introduces a dedicated sidecar process between TwinOps API and a Kit/mock
frame source — the missing link for a real GPU-to-browser path — without
building NVCF, TURN clusters, or multi-region.

## Decision

1. Ship `twinopsctl streaming-sidecar` as a separate process on `:8091`.
2. Enforce **one session / one GPU / one browser client**.
3. Provide session create/delete, health/ready, idle timeout, graceful shutdown,
   and Prometheus GPU metrics (`nvidia-smi` when present, honest zeros otherwise).
4. Default `frame_source=mock` (synthetic frames) for CI; optional `kit` mode
   supervises `TWINOPS_KIT_COMMAND` but does not yet capture RTX/NVENC frames.
5. TwinOps live API switches session mode to `kit-sidecar` when
   `TWINOPS_STREAMING_SIDECAR_URL` (or `--streaming-sidecar`) is set.
6. WebRTC answers remain lab-echo until a real encoder is wired.

## Consequences

- Clear process boundary for Kit streaming
- CI can validate session lifecycle without GPU
- Honest limitations documented; no false NVCF claims
- Path open for NVENC/App Streaming encoder in a later release
