#!/usr/bin/env bash
# Safe mock PLM engineering-change demo (temp copy — does not mutate the repo).
#
# Flow:
#   catalog synced → bump Robot01 revision → compare DRIFT → sync manifest → build
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/twinopsctl" ]]; then
  make install
fi

TWINOPSCTL="$ROOT/.venv/bin/twinopsctl"
WORK="$(mktemp -d /tmp/twinops-plm-demo.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

echo "==> Preparing temp example in $WORK"
mkdir -p "$WORK/assets"
cp "$ROOT/examples/assembly-line/twin.yaml" "$WORK/twin.yaml"
cp "$ROOT/examples/assembly-line/plm-catalog.json" "$WORK/plm-catalog.json"
cp "$ROOT/examples/assembly-line/assets/root.usda" "$WORK/assets/root.usda"

# Point baseStage at the temp assets copy.
"$ROOT/.venv/bin/python" - "$WORK/twin.yaml" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("baseStage: assets/root.usda", "baseStage: assets/root.usda")
path.write_text(text, encoding="utf-8")
PY

echo "==> Baseline compare"
"$TWINOPSCTL" plm compare --example "$WORK"

echo "==> Engineering change: bump Robot01 1004711"
"$TWINOPSCTL" plm bump 1004711 --example "$WORK"

echo "==> Compare after bump (expect DRIFT)"
set +e
"$TWINOPSCTL" plm compare --example "$WORK"
COMPARE_RC=$?
set -e
if [[ "$COMPARE_RC" -eq 0 ]]; then
  echo "expected DRIFT after bump" >&2
  exit 1
fi

echo "==> Sync catalog → twin.yaml"
"$TWINOPSCTL" plm sync --example "$WORK"

echo "==> Compare after sync (expect SYNCED)"
"$TWINOPSCTL" plm compare --example "$WORK"

echo "==> Compose stage with new PLM revision"
"$TWINOPSCTL" build "$WORK/twin.yaml" --out "$WORK/generated"
rg -n 'twinops:plmRevision = "D"' "$WORK/generated/plm-overlay.usda"

echo
echo "PLM change demo succeeded."
echo "Temp workdir was $WORK (cleaned on exit)."
