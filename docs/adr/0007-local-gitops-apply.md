# ADR-0007: Local GitOps apply for reconciliation proposals

## Status

Accepted (2026-07-31)

## Context

`twinopsctl reconcile` already emits overlay + PR draft artifacts, but demos
stopped at "open a PR manually". Operators need a safe local loop:
proposal → branch → commit → rebuild/drift, without pushing to remotes.

## Decision

Add `twinopsctl apply <proposal-dir>` that:

1. Checks out (or creates) `status.recommendedBranch`
2. Copies proposal artifacts into a target directory (default `usd/generated/applied`)
3. Writes an apply receipt JSON
4. Optionally `git add` + `git commit` when inside a git work tree
5. **Never** pushes to a remote

Remote PR automation (GitHub App) remains a later milestone.

## Consequences

- Demo scripts can show an end-to-end GitOps story on a laptop
- Apply is intentionally local-only to avoid accidental remote side effects
- Overlay still requires human review before merge
