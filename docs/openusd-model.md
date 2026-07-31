# OpenUSD Model

## Design principles

1. **Non-destructive overlays** — never rewrite vendor geometry assets in place.
2. **Composition over mutation** — use sublayers, references, and variants.
3. **Stable prim paths** — industrial identities map to fixed prim paths.
4. **Namespaced metadata** — TwinOps attributes live under `twinops:`.
5. **Git-friendly ASCII** — prefer `.usda` for reviewable diffs in PRs.

## Prim topology (assembly-line demo)

```text
/World
└── Factory
    └── LineA
        ├── Robot01
        ├── Conveyor01
        ├── Scanner01
        └── Packaging01
```

## Variants

`LineA` exposes an `ops` variant set:

| Variant           | Intent                         |
| ----------------- | ------------------------------ |
| `nominal`         | Default production mode        |
| `high-throughput` | Faster conveyor / denser cycle |
| `maintenance`     | Service / locked-out mode      |

The DigitalTwin manifest selects the active variant; the compiler writes a thin overlay that sets `ops = <variant>`.

## Custom attributes

| Attribute              | Type   | Source     | Purpose                    |
| ---------------------- | ------ | ---------- | -------------------------- |
| `twinops:plmItemId`    | string | PLM map    | Part / asset identity      |
| `twinops:plmRevision`  | string | PLM map    | Desired engineering rev    |
| `twinops:lifecycle`    | string | PLM map    | e.g. Released / Obsolete   |
| `twinops:temperature`       | float  | telemetry  | Live or default sensor        |
| `twinops:status`            | string | telemetry  | running / degraded / ...      |
| `twinops:firmware`          | string | telemetry  | Observed firmware version     |
| `twinops:<attr>Topic`       | string | telemetry  | MQTT topic for that attribute |

## Layer stack

```text
root.usda
  subLayers =
    @./variant-overlay.usda@
    @./telemetry-overlay.usda@
    @./plm-overlay.usda@
    @../assets/root.usda@   (or resolved baseStage)
```

Higher layers win for opinions. TwinOps overlays stay thin and metadata-focused.

## Validation rules (compiler)

- Manifest `apiVersion` / `kind` accepted
- Base stage path resolves
- Every mapped prim path is well-formed (`/`-absolute)
- Selected variant is declared on the base stage when discoverable
- Generated files are non-empty USDA ASCII
- Reconciliation report lists overlays, mappings, and warnings
