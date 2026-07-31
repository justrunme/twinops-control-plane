# TwinOps

**GitOps Control Plane for Industrial Digital Twins**

TwinOps is an experimental reference architecture that reconciles **PLM metadata**, **OpenUSD scene composition**, and **live telemetry** into a versioned, observable digital-twin runtime.

```text
PLM / ERP / IoT data
        ↓
Digital Twin Manifest (Git)
        ↓
TwinOps Compiler / Controller
        ↓
OpenUSD layers + variants
        ↓
Omniverse Kit (optional)
        ↓
Browser streaming (mock viewport now; Kit App Streaming later)
```

> Status: **experimental** (v0.3.7). Mock PLM adapter. Bidirectional MQTT. Optional Omniverse highlight contract. Not production-ready.

[![CI](https://github.com/justrunme/twinops-control-plane/actions/workflows/ci.yml/badge.svg)](https://github.com/justrunme/twinops-control-plane/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/justrunme/twinops-control-plane?display_name=tag)](https://github.com/justrunme/twinops-control-plane/releases/latest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![OpenUSD](https://img.shields.io/badge/OpenUSD-compiler-brightgreen.svg)](#2-minute-live-demo)
[![Go](https://img.shields.io/badge/Go-operator-brightgreen.svg)](docs/operator.md)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-CRD-brightgreen.svg)](docs/operator.md)
[![Omniverse](https://img.shields.io/badge/NVIDIA%20Omniverse-optional-orange.svg)](#roadmap)

---

## Why this exists

Most Omniverse demos show a beautiful 3D scene.  
Most Kubernetes demos show Helm, Terraform, and autoscaling.

TwinOps connects both worlds:

| DevOps                | TwinOps                   |
| --------------------- | ------------------------- |
| Kubernetes manifest   | DigitalTwin manifest      |
| container image       | USD asset                 |
| configuration overlay | USD layer                 |
| environment           | scene variant             |
| GitOps reconciliation | stage composition         |
| deployment rollout    | twin revision rollout     |
| runtime metrics       | telemetry and scene state |
| drift detection       | PLM / scene / IoT drift   |
| rollback              | previous USD composition  |

The distinctive feature is **three-way drift detection**:

```text
Desired state  — Git / PLM
Rendered state — OpenUSD Stage
Observed state — IoT telemetry
```

When those diverge, TwinOps surfaces the drift and can propose a Git-backed reconciliation.

---

## 2-minute live demo

No GPU required.

```bash
git clone https://github.com/justrunme/twinops-control-plane.git
cd twinops-control-plane
make install
make live-demo
```

Open **http://127.0.0.1:8080/**

```text
1. Trigger heat spike      → CRITICAL / DRIFT + scene highlight
2. Apply reconciliation    → USD overlay + healed telemetry
3. Twin returns to SYNCED  → timeline + mock Kit viewport calm
```

Smoke check without a browser:

```bash
make live-demo-smoke
```

Full walkthrough: [docs/demo.md](docs/demo.md)

---

## Quickstart extras

### Offline CLI demo

```bash
make demo
```

Produces composed USDA layers, a drift HTML report, and a GitOps reconciliation proposal.

### MQTT publish + ingest

```bash
make mqtt-smoke
twinopsctl mqtt topics
```

Starts Mosquitto, publishes simulator telemetry, injects an external PLC heat spike, and asserts CRITICAL drift.
Topic catalog: `examples/assembly-line/mqtt-topics.json` / `GET /api/mqtt/topics`.

### Mock PLM adapter

```bash
twinopsctl plm show
twinopsctl plm compare
```

See [docs/plm-adapter.md](docs/plm-adapter.md).

### Omniverse highlight contract (no GPU)

```bash
make serve
# other terminal:
make scene-live      # fetch + validate /api/scene
make scene-highlight # Kit stub client
make scene           # offline JSON + HTML highlight report
```

See [docs/omniverse.md](docs/omniverse.md).

### Local DX probes

```bash
make doctor
make live-status
make timeline
twinopsctl proposal
twinopsctl live spike
twinopsctl live reconcile
make scene-live
twinopsctl openapi --out /tmp/twinops-openapi.json
make verify-all
```

Docs index: [docs/README.md](docs/README.md). Security: [SECURITY.md](SECURITY.md).

### Dev UI (Vite hot reload)

```bash
make serve      # terminal 1 — API :8080
make web-dev    # terminal 2 — UI  :5173
```

### Kubernetes operator

```bash
make operator-demo          # k3d preferred, kind fallback
make operator-demo-cleanup

# or against an existing kubeconfig:
make operator-build
# kubectl apply -f config/crd/bases/twinops.io_digitaltwins.yaml
# make operator-run
```

See [docs/operator.md](docs/operator.md) and [docs/live-telemetry.md](docs/live-telemetry.md).

### Tests

```bash
make test
make go-test
make verify-all
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## DigitalTwin manifest

```yaml
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: assembly-line-a
spec:
  source:
    baseStage: assets/root.usda

  configuration:
    variant: high-throughput

  telemetry:
    provider: mqtt
    endpoint: mqtt://factory-broker
    mappings:
      - topic: factory/robot-01/temperature
        prim: /World/Factory/LineA/Robot01
        attribute: twinops:temperature

  plm:
    provider: mock
    mappings:
      - itemId: "1004711"
        revision: "C"
        prim: /World/Factory/LineA/Robot01

  streaming:
    enabled: false
    gpuClass: graphics
    idleTimeout: 20m
```

The compiler turns this into OpenUSD overlay layers with `twinops:*` custom attributes, references, and a selected scene variant.

---

## Repository layout

```text
twinops-control-plane/
├── python/twinops/          # Compiler, drift, live API, PLM mock, CLI
├── examples/assembly-line/  # Demo factory line + sample USDA + PLM/MQTT catalogs
├── scripts/                 # live-demo / mqtt-smoke / operator-demo / sync helpers
├── docs/                    # Architecture, USD model, ADRs, roadmap
├── api/                     # DigitalTwin CRD types (Go)
├── controllers/             # Kubernetes operator controllers
├── cmd/manager/             # Operator manager entrypoint
├── deploy/helm/             # Helm chart for the operator
├── Dockerfile.live          # Demo live API + web UI image
├── Dockerfile.operator      # Operator manager image
├── extensions/              # Omniverse Kit highlight stub
├── usd/                     # Generated / shared USD workspace
└── web/                     # Live control-plane UI + mock Kit viewport
```

About **70% of the platform** (compiler, drift engine, operator, GitOps, observability, mock adapters) can be built **without an NVIDIA GPU**. GPU is required only for Kit rendering and streaming.

---

## Demo story: Self-Healing Production Line

```text
Robot → Conveyor → Scanner → Packaging
```

1. Change desired robot revision in Git  
2. TwinOps compiles a new USD overlay layer  
3. Drift engine compares desired / rendered / observed state  
4. Scene metadata highlights revision or telemetry drift  
5. A reconciliation proposal restores the desired composition  

Milestones 1–2 deliver composition, drift detection, HTML report, and a reconciliation proposal. The Kubernetes operator reconciles `DigitalTwin` CRs via `twinopsctl`.

---

## Roadmap

| Milestone | Focus                                      | Status      |
| --------- | ------------------------------------------ | ----------- |
| 0         | Repository foundation, docs, sample scene  | **done**    |
| 1         | OpenUSD Digital Twin Compiler + CLI        | **done**    |
| 2         | Drift engine + reconcile proposal + demo   | **done**    |
| 3         | Kubernetes operator + DigitalTwin CRD      | **done**    |
| 4         | Live MQTT telemetry + drift API            | **done**    |
| 5         | Web control plane + one-command live demo  | **done**    |
| 6         | Omniverse highlight + mock Kit viewport    | **foundation** |
| —         | Mock PLM adapter CLI                       | **done**    |

See [docs/roadmap.md](docs/roadmap.md) and [docs/architecture.md](docs/architecture.md).

---

## What we will not claim yet

Until the corresponding runtime exists, this project does **not** claim:

- production-ready / enterprise-ready
- NVCF support
- vendor-specific PLM product integration
- full Omniverse Kit App Streaming deployment

PLM integration starts as a **generic mock adapter**.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
