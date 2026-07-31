#!/usr/bin/env bash
# Offline GitOps demo: compose → drift → reconcile → apply --verify.
#
# Usage:
#   ./scripts/demo_gitops.sh
#   EXAMPLE=examples/assembly-line ./scripts/demo_gitops.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EXAMPLE="${EXAMPLE:-examples/assembly-line}"
PROPOSAL="${PROPOSAL:-/tmp/twinops-proposal}"
STAGE_OUT="${STAGE_OUT:-/tmp/twinops-apply-verify}"
TWINOPSCTL="${TWINOPSCTL:-${ROOT}/.venv/bin/twinopsctl}"

if [[ ! -x "${TWINOPSCTL}" ]]; then
  echo "==> Installing TwinOps (make install)"
  make install
fi

echo "==> Compose + drift"
make drift

echo "==> Reconcile proposal → ${PROPOSAL}"
"${TWINOPSCTL}" reconcile \
  --desired "${EXAMPLE}/desired.yaml" \
  --stage "${EXAMPLE}/generated/root.usda" \
  --observed "${EXAMPLE}/telemetry.json" \
  --manifest "${EXAMPLE}/twin.yaml" \
  --out "${PROPOSAL}"

echo "==> Apply + verify (local only, no push)"
set +e
"${TWINOPSCTL}" apply "${PROPOSAL}" --no-commit --no-branch --print-pr --verify \
  --manifest "${EXAMPLE}/twin.yaml" \
  --desired "${EXAMPLE}/desired.yaml" \
  --observed "${EXAMPLE}/telemetry.json" \
  --stage-out "${STAGE_OUT}" \
  --json
code=$?
set -e

echo "==> Done (exit=${code})"
echo "    Note: exit 1 can mean remaining drift after an empty/partial overlay — expected for sample telemetry."
exit 0
