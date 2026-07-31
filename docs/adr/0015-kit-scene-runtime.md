# ADR-0015: Omniverse Kit as an optional scene runtime

## Status

Accepted

## Context

TwinOps is a GitOps control plane for digital twins. Omniverse Kit is one
optional runtime for OpenUSD visualization — not the center of the product.
Milestone 6 shipped a highlight contract and a stub extension. v0.7 turns that
stub into a real runtime loop with pluggable apply backends.

## Decision

1. Keep `twinops.highlight.v1` as the only contract between control plane and runtime.
2. Ship `TwinOpsSceneRuntime` with backends:
   - `plan` — CI / laptop (print plan)
   - `overlay` — write highlight USDA without Kit/pxr
   - `kit` — `omni.usd` displayColor + selection inside Kit
3. Kit extension starts a background poll/WS loop and applies via `KitUsdApplier`.
4. Kit App Streaming (GPU frames to browser) remains a later sidecar on top of
   the lab WebRTC signaling path (ADR-0014).

## Consequences

- Demos and CI stay GPU-free
- Real Kit installs get live prim highlighting
- Omniverse stays optional; Kubernetes/GitOps story stays primary
