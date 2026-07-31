#!/usr/bin/env bash
# TwinOps 2-minute live demo.
#
# Usage:
#   ./scripts/live_demo.sh           # build UI, start API+UI on :8080
#   ./scripts/live_demo.sh --smoke   # start, run spike→reconcile, stop
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HOST="${TWINOPS_HOST:-127.0.0.1}"
PORT="${TWINOPS_PORT:-8080}"
BASE="http://${HOST}:${PORT}"
SMOKE=0
KEEP_LOG="${TWINOPS_DEMO_LOG:-/tmp/twinops-live-demo.log}"

for arg in "$@"; do
  case "$arg" in
    --smoke) SMOKE=1 ;;
    -h|--help)
      sed -n '2,7p' "$0"
      exit 0
      ;;
  esac
done

if [[ ! -x "$ROOT/.venv/bin/twinopsctl" ]]; then
  echo "==> Installing TwinOps (make install)"
  make install
fi

TWINOPSCTL="$ROOT/.venv/bin/twinopsctl"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -f "$ROOT/web/dist/index.html" ]]; then
  echo "==> Building web control plane"
  make web
fi

echo "==> Starting TwinOps live API on ${BASE}"
"$TWINOPSCTL" serve \
  --example examples/assembly-line \
  --host "$HOST" \
  --port "$PORT" \
  --web-dist web/dist \
  --interval 1.0 \
  >"$KEEP_LOG" 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}

if [[ "$SMOKE" -eq 1 ]]; then
  trap cleanup EXIT
else
  trap 'echo; echo "Stopped TwinOps live demo."; cleanup' INT TERM
fi

echo -n "==> Waiting for health"
for _ in $(seq 1 40); do
  if curl -fsS "$BASE/api/health" >/dev/null 2>&1; then
    echo " OK"
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo
    echo "Server exited early. Log: $KEEP_LOG"
    tail -n 40 "$KEEP_LOG" || true
    exit 1
  fi
  echo -n "."
  sleep 0.25
done

if ! curl -fsS "$BASE/api/health" >/dev/null 2>&1; then
  echo
  echo "Timed out waiting for $BASE/api/health"
  tail -n 40 "$KEEP_LOG" || true
  exit 1
fi

echo "==> Demo flow: spike → reconcile → SYNCED"
SPIKE_JSON="$(curl -fsS -X POST "$BASE/api/simulate/spike")"
printf '%s' "$SPIKE_JSON" | "$PYTHON" -c "
import json, sys
payload = json.load(sys.stdin)
status = payload.get('drift', {}).get('status', {})
print(f\"    spike: hasDrift={status.get('hasDrift')} summary={status.get('summary')}\")
"

RECON_JSON="$(curl -fsS -X POST "$BASE/api/reconcile")"
printf '%s' "$RECON_JSON" | "$PYTHON" -c "
import json, sys
payload = json.load(sys.stdin)
status = payload.get('drift', {}).get('status', {})
print(
    f\"    reconcile: changes={payload.get('changes')} \"
    f\"hasDrift={status.get('hasDrift')} summary={status.get('summary')}\"
)
if status.get('hasDrift'):
    raise SystemExit('expected SYNCED after reconcile')
print('    result: SYNCED')
"

cat <<EOF

TwinOps live demo is ready.

  UI:         ${BASE}/
  Health:     ${BASE}/api/health
  Twin:       ${BASE}/api/twin
  Spike:      curl -X POST ${BASE}/api/simulate/spike
  Reconcile:  curl -X POST ${BASE}/api/reconcile

Demo path in UI:
  1. Trigger heat spike
  2. Apply reconciliation
  3. Watch timeline return to SYNCED

Log file: ${KEEP_LOG}
EOF

if [[ "$SMOKE" -eq 1 ]]; then
  echo "==> Smoke demo passed"
  exit 0
fi

echo
echo "Server running (pid ${SERVER_PID}). Press Ctrl+C to stop."
wait "$SERVER_PID"
