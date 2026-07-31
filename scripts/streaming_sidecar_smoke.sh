#!/usr/bin/env bash
# Smoke: start streaming sidecar, create session, offer, frame, delete.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HOST="${TWINOPS_SIDECAR_HOST:-127.0.0.1}"
PORT="${TWINOPS_SIDECAR_PORT:-18091}"
BASE="http://${HOST}:${PORT}"
TWINOPSCTL="${TWINOPSCTL:-${ROOT}/.venv/bin/twinopsctl}"
PYTHON="${PYTHON:-${ROOT}/.venv/bin/python}"
LOG="${TMPDIR:-/tmp}/twinops-sidecar-smoke.log"

if [[ ! -x "${TWINOPSCTL}" ]]; then
  make install
fi

"${TWINOPSCTL}" streaming-sidecar --host "${HOST}" --port "${PORT}" --idle-timeout 120 \
  >"${LOG}" 2>&1 &
PID=$!

cleanup() {
  if kill -0 "${PID}" 2>/dev/null; then
    kill "${PID}" 2>/dev/null || true
    wait "${PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo -n "==> Waiting for sidecar health"
for _ in $(seq 1 40); do
  if curl -fsS "${BASE}/health" >/dev/null 2>&1; then
    echo " OK"
    break
  fi
  if ! kill -0 "${PID}" 2>/dev/null; then
    echo
    tail -n 40 "${LOG}" || true
    exit 1
  fi
  echo -n "."
  sleep 0.25
done

curl -fsS "${BASE}/ready" | "${PYTHON}" -c "
import json,sys
data=json.load(sys.stdin)
assert data.get('status')=='ready', data
print('    ready:', data)
"

curl -fsS -X POST "${BASE}/v1/sessions" -H 'content-type: application/json' \
  -d '{"clientId":"smoke"}' >"${TMPDIR:-/tmp}/twinops-sidecar-session.json"
SID="$("${PYTHON}" -c "import json; print(json.load(open('${TMPDIR:-/tmp}/twinops-sidecar-session.json'))['session']['sessionId'])")"

curl -fsS -X POST "${BASE}/v1/sessions/${SID}/signal" \
  -H 'content-type: application/json' \
  -d '{"action":"offer","sdp":{"type":"offer","sdp":"v=0"}}' \
  | "${PYTHON}" -c "
import json,sys
data=json.load(sys.stdin)
assert data.get('ok') and data.get('answer',{}).get('labEcho')
print('    offer/answer OK')
"

curl -fsS -X POST "${BASE}/v1/sessions/${SID}/frame" \
  | "${PYTHON}" -c "
import json,sys
data=json.load(sys.stdin)
assert data.get('ok'), data
print('    frame', data.get('frame'))
"

code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE}/v1/sessions" -H 'content-type: application/json' -d '{}')"
test "${code}" = "409"
echo "    single-session limit OK (HTTP 409)"

curl -fsS -X DELETE "${BASE}/v1/sessions/${SID}" >/dev/null
echo "streaming-sidecar smoke OK"
