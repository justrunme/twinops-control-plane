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

READY_JSON="$(curl -fsS "$BASE/api/ready")"
printf '%s' "$READY_JSON" | "$PYTHON" -c "
import json, sys
payload = json.load(sys.stdin)
if payload.get('status') != 'ready':
    raise SystemExit(f\"expected ready, got {payload!r}\")
print(f\"    ready: twin={payload.get('twin')} hasDriftReport={payload.get('hasDriftReport')}\")
"

echo "==> Demo flow: spike → scene highlight → reconcile → SYNCED"
SPIKE_JSON="$("$TWINOPSCTL" live spike --base-url "$BASE" --json)"
printf '%s' "$SPIKE_JSON" | "$PYTHON" -c "
import json, sys
payload = json.load(sys.stdin)
status = payload.get('drift', {}).get('status', {})
print(f\"    spike: hasDrift={status.get('hasDrift')} summary={status.get('summary')}\")
"

SCENE_JSON="$(curl -fsS "$BASE/api/scene")"
printf '%s' "$SCENE_JSON" | "$PYTHON" -c "
import json, sys
scene = json.load(sys.stdin)
lit = [p for p in scene.get('prims', []) if (p.get('highlight') or {}).get('enabled')]
robot = next((p for p in scene.get('prims', []) if p.get('label') == 'Robot01'), None)
print(f\"    scene: protocol={scene.get('protocol', {}).get('name')} lit={len(lit)}\")
if not lit:
    raise SystemExit('expected highlighted prims after spike')
if not robot or not (robot.get('highlight') or {}).get('enabled'):
    raise SystemExit('expected Robot01 highlight after spike')
print(f\"    scene: Robot01 status={robot.get('status')}\")
"

SCENE_HTML="$(curl -fsS "$BASE/api/scene/report")"
printf '%s' "$SCENE_HTML" | "$PYTHON" -c "
import sys
html = sys.stdin.read()
if 'Scene' not in html and 'highlight' not in html.lower():
    raise SystemExit('expected HTML scene report after spike')
print('    scene: HTML report OK')
"

RECON_JSON="$("$TWINOPSCTL" live reconcile --base-url "$BASE" --json)"
printf '%s' "$RECON_JSON" | "$PYTHON" -c "
import json, sys
payload = json.load(sys.stdin)
status = payload.get('drift', {}).get('status', {})
scene = payload.get('scene') or {}
lit = [p for p in scene.get('prims', []) if (p.get('highlight') or {}).get('enabled')]
print(
    f\"    reconcile: changes={payload.get('changes')} \"
    f\"hasDrift={status.get('hasDrift')} summary={status.get('summary')} lit={len(lit)}\"
)
if status.get('hasDrift'):
    raise SystemExit('expected SYNCED after reconcile')
print('    result: SYNCED')
"

cat <<EOF

TwinOps live demo is ready.

  UI:         ${BASE}/
  Health:     ${BASE}/api/health
  Ready:      ${BASE}/api/ready
  Twin:       ${BASE}/api/twin
  Scene HTML: ${BASE}/api/scene/report
  MQTT map:   ${BASE}/api/mqtt/topics
  Swagger:    ${BASE}/docs
  Spike:      twinopsctl live spike
  Reconcile:  twinopsctl live reconcile

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
