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
Browser streaming (planned)
```

> Status: **experimental**. Mock PLM adapter. Optional Omniverse runtime. Streaming integration planned. Not production-ready.

[![CI](https://github.com/justrunme/twinops-control-plane/actions/workflows/ci.yml/badge.svg)](https://github.com/justrunme/twinops-control-plane/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Go](https://img.shields.io/badge/Go-operator%20planned-gray.svg)](#roadmap)
[![OpenUSD](https://img.shields.io/badge/OpenUSD-compiler-brightgreen.svg)](#quickstart)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-operator%20planned-gray.svg)](#roadmap)
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

## Quickstart (no GPU required)

```bash
git clone https://github.com/justrunme/twinops-control-plane.git
cd twinops-control-plane
make install
make demo
```

`make demo` runs the self-healing scenario:

1. Compose the assembly-line OpenUSD stage  
2. Inject a stale PLM revision into the rendered scene  
3. Compare desired / rendered / observed telemetry  
4. Emit drift table, HTML dashboard, and a GitOps reconciliation proposal  

Manual commands:

```bash
twinopsctl build examples/assembly-line/twin.yaml --out examples/assembly-line/generated

twinopsctl drift \
  --desired examples/assembly-line/desired.yaml \
  --stage examples/assembly-line/demo-run/stage/root.usda \
  --observed examples/assembly-line/telemetry.json \
  --manifest examples/assembly-line/twin.yaml \
  --out examples/assembly-line/demo-run/drift \
  --propose examples/assembly-line/demo-run/proposal
```

Artifacts:

```text
examples/assembly-line/demo-run/
├── stage/                     # composed USDA layers
├── drift/drift-report.html    # color-coded dashboard
└── proposal/
    ├── reconcile-overlay.usda
    ├── reconciliation-proposal.json
    └── PULL_REQUEST.md
```

Live telemetry API (no external broker required):

```bash
make serve
# GET  http://127.0.0.1:8080/api/twin
# POST http://127.0.0.1:8080/api/simulate/spike
# WS   ws://127.0.0.1:8080/ws/events
```

See [docs/live-telemetry.md](docs/live-telemetry.md).

Web control plane (timeline UI):

```bash
# terminal 1
make serve

# terminal 2
make web-dev
# open http://127.0.0.1:5173
```

Or build UI into the API:

```bash
make web && make serve
# open http://127.0.0.1:8080/
```

Operator:

```bash
make operator-build
# kubectl apply -f config/crd/bases/twinops.io_digitaltwins.yaml
# make operator-run
```

See [docs/operator.md](docs/operator.md).

Run tests:

```bash
make test
make go-test
```

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
├── python/twinops/          # Compiler + drift engine + CLI
├── examples/assembly-line/  # Demo factory line + sample USDA
├── scripts/                 # End-to-end demo scripts
├── docs/                    # Architecture, USD model, ADRs, roadmap
├── api/                     # DigitalTwin CRD types (Go)
├── controllers/             # Kubernetes operator controllers
├── cmd/manager/             # Operator manager entrypoint
├── deploy/helm/             # Helm chart for the operator
├── usd/                     # Generated / shared USD workspace
├── web/                     # Live control-plane UI
└── kit-app/                 # Planned Omniverse Kit extension
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
| 5         | Web control plane (timeline UI)            | **done**    |
| 6         | Omniverse Kit extension / GPU streaming    | planned     |

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
