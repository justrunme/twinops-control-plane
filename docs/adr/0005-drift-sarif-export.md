# ADR-0005: Drift findings as SARIF

## Status

Accepted

## Context

CI and code-scanning UIs understand SARIF. TwinOps drift is not source linting,
but findings map cleanly to SARIF results for PR annotations and artifact upload.

## Decision

When `twinopsctl drift --out …` runs, also write `drift-report.sarif`.
Optional `--sarif PATH` writes (or overrides) an explicit SARIF destination.

Only non-SYNCED findings become SARIF results. Levels:

| Drift status | SARIF level |
| --- | --- |
| CRITICAL / DRIFT / MISSING | error |
| WARNING | warning |

Tool driver name remains `twinopsctl`.

## Consequences

### Positive

- `upload-sarif` / artifact consumers can display twin drift without a custom UI
- Keeps JSON + HTML reports as the primary human formats

### Negative / trade-offs

- Logical locations use prim paths, not filesystem URIs
- Not a substitute for GitHub CodeQL
