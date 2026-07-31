#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EXAMPLE="$ROOT/examples/assembly-line"
OUT="$EXAMPLE/demo-run"
STAGE_DIR="$OUT/stage"
DRIFT_DIR="$OUT/drift"
PROPOSAL_DIR="$OUT/proposal"

if [[ -x "$ROOT/.venv/bin/twinopsctl" ]]; then
  TWINOPSCTL="$ROOT/.venv/bin/twinopsctl"
elif command -v twinopsctl >/dev/null 2>&1; then
  TWINOPSCTL="twinopsctl"
else
  echo "twinopsctl not found. Run: make install" >&2
  exit 1
fi

rm -rf "$OUT"
mkdir -p "$STAGE_DIR" "$DRIFT_DIR" "$PROPOSAL_DIR"

echo "==> 1/4 Compose digital twin"
"$TWINOPSCTL" build "$EXAMPLE/twin.yaml" --out "$STAGE_DIR"

echo
echo "==> 2/4 Inject stale USD revision (simulate forgotten PLM sync)"
# Robot01 in USD still on revision B while Git/PLM desire C.
python3 - <<'PY' "$STAGE_DIR/plm-overlay.usda"
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
# Only rewrite the Robot01 block's revision: first plmRevision in file is Robot01
# because overlays are emitted in sorted prim order:
# Conveyor01, Packaging01, Robot01, Scanner01 — so replace carefully.
import re
pattern = re.compile(
    r'(over "Robot01"\s*\{.*?custom string twinops:plmRevision = ")([^"]+)(")',
    re.S,
)
updated, count = pattern.subn(r"\1B\3", text, count=1)
if count != 1:
    raise SystemExit("failed to inject stale Robot01 revision")
path.write_text(updated, encoding="utf-8")
print(f"patched {path}: Robot01 twinops:plmRevision -> B")
PY

echo
echo "==> 3/4 Detect three-way drift"
set +e
"$TWINOPSCTL" drift \
  --desired "$EXAMPLE/desired.yaml" \
  --stage "$STAGE_DIR/root.usda" \
  --observed "$EXAMPLE/telemetry.json" \
  --manifest "$EXAMPLE/twin.yaml" \
  --out "$DRIFT_DIR" \
  --propose "$PROPOSAL_DIR"
DRIFT_RC=$?
set -e

echo
echo "==> 4/4 Artifacts"
echo "Stage:     $STAGE_DIR"
echo "Drift UI:  $DRIFT_DIR/drift-report.html"
echo "Proposal:  $PROPOSAL_DIR/PULL_REQUEST.md"
echo "Overlay:   $PROPOSAL_DIR/reconcile-overlay.usda"
echo
if [[ -f "$DRIFT_DIR/drift-report.html" ]]; then
  echo "Open drift dashboard:"
  echo "  open $DRIFT_DIR/drift-report.html"
fi
echo
echo "Demo finished with drift exit code: $DRIFT_RC"
exit 0
