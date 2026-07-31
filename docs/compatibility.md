# Compatibility matrix (TwinOps 1.0)

Reference architecture — validated locally and in GitHub Actions on Ubuntu.

| Component | Supported | Notes |
|-----------|-----------|-------|
| Python | **3.11, 3.12** | 3.13 lab-ok; CI matrix is 3.11/3.12 |
| Go (operator) | **1.26.x** | as in CI |
| Kubernetes | **1.27+** (kind/lab) | operator uses controller-runtime |
| Helm | **3.12+** | umbrella chart `deploy/helm/twinops` |
| Node (web UI) | **22.x** | Vite build |
| MQTT | Mosquitto **2.x** | lab compose under `deploy/demo/` |
| Omniverse Kit | optional | extension tested via session-layer unit tests; full Kit GPU path is lab |
| Streaming sidecar | mock frames (CI) | Kit supervisor via `TWINOPS_KIT_COMMAND`; NVENC not in 1.0 |
| OS | Linux (CI), macOS (dev) | Windows: WSL2 recommended |

## API / contract stability (1.0)

Treated as stable for reference demos:

- `twinops.highlight.v1` scene contract
- Live HTTP/WS control API (`/api/*`, `/ws/events`)
- `TwinIncident` JSON + `incident replay --verify`
- `PlmAdapter` protocol (File + REST)
- Kit streaming session descriptor (`mock` / `lab-webrtc` / `kit-sidecar`)
- SQLite persistence schema used by `serve --db`

## Explicitly unstable / experimental

- Proprietary PLM SDKs (out of tree)
- Real RTX → browser MediaStream encoder
- Multi-session / multi-GPU streaming
- Remote GitHub App apply automation
