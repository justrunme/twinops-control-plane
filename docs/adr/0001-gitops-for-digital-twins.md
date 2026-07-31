# ADR-0001: GitOps for Digital Twins

## Status

Accepted

## Context

Industrial digital twins combine PLM metadata, 3D scene composition (OpenUSD), and live IoT telemetry. Existing Omniverse and Kubernetes materials show how to deploy runtimes, but do not define a portable control-plane model for *desired twin state*.

We need a model that:

- is reviewable in Git (PRs, rollbacks, audit trail);
- composes OpenUSD non-destructively;
- can later reconcile against physical observations;
- does not require a GPU for the majority of the platform.

## Decision

Adopt a **GitOps control-plane** metaphor:

1. Desired twin state is declared as a `DigitalTwin` manifest (YAML / future CRD).
2. A compiler (and later a Kubernetes operator) produces OpenUSD overlay layers.
3. Drift compares **desired**, **rendered**, and **observed** states.
4. Reconciliation proposals return as Git changes (layers / manifest updates).

OpenUSD is the composition substrate because layers, references, payloads, and variants naturally map to infrastructure overlays and environment variants.

## Consequences

### Positive

- Familiar DevOps workflows apply to industrial 3D systems.
- ~70% of the stack is GPU-free and CI-friendly.
- Keeps the control plane portable and reviewable without a GPU runtime.

### Negative / trade-offs

- Full visual demos still need Omniverse / GPU later.
- Pure-text USDA generation is used until optional `pxr` validation is added.
- PLM starts as a mock adapter to avoid vendor-specific IP.

## Alternatives considered

1. **Pure Omniverse extension** — strong UX, weak GitOps / platform story.
2. **Only Kubernetes operator wrapping NVIDIA OVAS** — useful, but mostly deployment glue.
3. **Heavy PLM-native integration first** — high coupling, weak portable open-source demo fit.
