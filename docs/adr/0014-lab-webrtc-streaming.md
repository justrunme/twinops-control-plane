# ADR-0014: Lab WebRTC streaming path

## Status

Accepted (lab)

## Context

ADR-0012 defined a mock Kit streaming session. Callers need a real browser
WebRTC path before NVIDIA Kit App Streaming is available.

## Decision

When `TWINOPS_WEBRTC=1` or `twinopsctl serve --webrtc`:

- Session `metadata.mode` becomes `lab-webrtc`
- `spec.webrtc.enabled=true` with REST signaling at
  `/api/streaming/webrtc/signal`
- Web UI captures a scene canvas via `captureStream()` and registers an SDP
  offer with the signaling hub
- Media remains lab/browser-local until a Kit App Streaming sidecar supplies
  a real answer + GPU frames

## Consequences

- Demonstrates WebRTC signaling + MediaStream without NVCF/GPU
- Same session contract upgrades to Kit App Streaming later by changing
  `provider` / `streamUrl` / answer source
