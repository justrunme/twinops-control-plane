#!/usr/bin/env bash
# TwinOps portfolio end-to-end scenario (v0.10).
#
# PLM → compose → spike → CRITICAL → highlight → incident → proposal →
# apply/verify → SYNCED → incident replay --verify
#
# Usage:
#   ./scripts/portfolio_demo.sh
#   ARTIFACTS=/tmp/twinops-portfolio ./scripts/portfolio_demo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HOST="${TWINOPS_HOST:-127.0.0.1}"
PORT="${TWINOPS_PORT:-18080}"
BASE="http://${HOST}:${PORT}"
EXAMPLE="${EXAMPLE:-examples/assembly-line}"
ARTIFACTS="${ARTIFACTS:-/tmp/twinops-portfolio-demo}"
LOG="${ARTIFACTS}/server.log"
TWINOPSCTL="${TWINOPSCTL:-${ROOT}/.venv/bin/twinopsctl}"
PYTHON="${PYTHON:-${ROOT}/.venv/bin/python}"

if [[ ! -x "${TWINOPSCTL}" ]]; then
  echo "==> Installing TwinOps (make install)"
  make install
fi

rm -rf "${ARTIFACTS}"
mkdir -p "${ARTIFACTS}/"{out,work,db,proposal}

if [[ ! -f "${ROOT}/web/dist/index.html" ]]; then
  echo "==> Building web control plane"
  make web
fi

echo "==> PLM desired revision (File adapter)"
"${TWINOPSCTL}" plm show --catalog "${EXAMPLE}/plm-catalog.json" --json \
  >"${ARTIFACTS}/out/plm-catalog.json"

echo "==> Starting TwinOps live API (SQLite persistence) on ${BASE}"
"${TWINOPSCTL}" serve \
  --example "${EXAMPLE}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --work-dir "${ARTIFACTS}/work" \
  --db "${ARTIFACTS}/db/twinops.sqlite" \
  --web-dist web/dist \
  --interval 0.5 \
  >"${LOG}" 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo -n "==> Waiting for health"
for _ in $(seq 1 60); do
  if curl -fsS "${BASE}/api/health" >/dev/null 2>&1; then
    echo " OK"
    break
  fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    echo
    echo "Server exited early. Log: ${LOG}"
    tail -n 60 "${LOG}" || true
    exit 1
  fi
  echo -n "."
  sleep 0.25
done

if ! curl -fsS "${BASE}/api/health" >/dev/null 2>&1; then
  echo
  echo "Timed out waiting for ${BASE}/api/health"
  tail -n 60 "${LOG}" || true
  exit 1
fi

echo "==> MQTT heat spike → CRITICAL drift"
SPIKE_JSON="$("${TWINOPSCTL}" live spike --base-url "${BASE}" --json)"
printf '%s' "${SPIKE_JSON}" | "${PYTHON}" -c "
import json, sys
payload = json.load(sys.stdin)
status = payload.get('drift', {}).get('status', {})
summary = status.get('summary') or {}
print(f\"    spike: hasDrift={status.get('hasDrift')} summary={summary}\")
if not status.get('hasDrift'):
    raise SystemExit('expected drift after heat spike')
if int(summary.get('CRITICAL') or 0) < 1:
    raise SystemExit('expected CRITICAL finding after heat spike')
"

echo "==> Kit highlight contract (scene.v1)"
SCENE_JSON="$("${TWINOPSCTL}" scene --from-url "${BASE}" --strict --json || true)"
printf '%s' "${SCENE_JSON}" >"${ARTIFACTS}/out/scene.json"
printf '%s' "${SCENE_JSON}" | "${PYTHON}" -c "
import json, sys
scene = json.load(sys.stdin)
lit = [p for p in scene.get('prims', []) if (p.get('highlight') or {}).get('enabled')]
print(f\"    highlight: lit={len(lit)}\")
if not lit:
    raise SystemExit('expected highlighted prims after spike')
"

# GPU-free highlight overlay apply (Kit session-layer substitute in CI).
EXT="${ROOT}/extensions/twinops_highlight"
PYTHONPATH="${EXT}${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON}" -m twinops_highlight.client \
  --base-url "${BASE}" \
  --apply overlay \
  --overlay-out "${ARTIFACTS}/out/highlight-overlay.usda" \
  >"${ARTIFACTS}/out/highlight-apply.txt"
test -f "${ARTIFACTS}/out/highlight-overlay.usda"

curl -fsS "${BASE}/api/scene/report" >"${ARTIFACTS}/out/scene.html"
curl -fsS "${BASE}/api/drift/report" >"${ARTIFACTS}/out/drift.html"
curl -fsS "${BASE}/api/drift/latest" >"${ARTIFACTS}/out/drift-latest.json"

echo "==> Incident recording (timeline export)"
"${TWINOPSCTL}" incident export \
  --from-url "${BASE}" \
  --twin assembly-line-a \
  --out "${ARTIFACTS}/out/incident-mid.json"

echo "==> Reconciliation proposal + live apply → SYNCED"
RECON_JSON="$("${TWINOPSCTL}" live reconcile --base-url "${BASE}" --json)"
printf '%s' "${RECON_JSON}" >"${ARTIFACTS}/out/reconcile.json"
printf '%s' "${RECON_JSON}" | "${PYTHON}" -c "
import json, sys
payload = json.load(sys.stdin)
status = payload.get('drift', {}).get('status', {})
print(
    f\"    reconcile: changes={payload.get('changes')} \"
    f\"hasDrift={status.get('hasDrift')} summary={status.get('summary')}\"
)
if status.get('hasDrift'):
    raise SystemExit('expected SYNCED after reconcile')
"

echo "==> Persist observed snapshot for apply/replay"
curl -fsS "${BASE}/api/twin" | "${PYTHON}" -c "
import json, sys
from pathlib import Path
snap = json.load(sys.stdin)
observed = snap.get('observed')
path = Path('${ARTIFACTS}/work/observed-latest.json')
if isinstance(observed, dict) and observed.get('observations'):
    path.write_text(json.dumps(observed, indent=2) + '\n', encoding='utf-8')
else:
    path.write_text(Path('${EXAMPLE}/telemetry.json').read_text(encoding='utf-8'), encoding='utf-8')
"

echo "==> Git-backed apply --verify (local, no push)"
set +e
"${TWINOPSCTL}" apply --from-url "${BASE}" \
  --no-commit --no-branch --print-pr --verify \
  --manifest "${EXAMPLE}/twin.yaml" \
  --desired "${EXAMPLE}/desired.yaml" \
  --observed "${ARTIFACTS}/work/observed-latest.json" \
  --stage-out "${ARTIFACTS}/proposal/verify-stage" \
  --json >"${ARTIFACTS}/out/apply-verify.json" 2>"${ARTIFACTS}/out/apply-verify.err"
APPLY_CODE=$?
set -e

echo "==> Export final incident + artifacts"
"${TWINOPSCTL}" incident export \
  --from-url "${BASE}" \
  --twin assembly-line-a \
  --out "${ARTIFACTS}/out/incident.json"

# SARIF from offline drift against post-reconcile stage when available.
STAGE="${ARTIFACTS}/work/stage/root.usda"
if [[ -f "${STAGE}" ]]; then
  "${TWINOPSCTL}" drift \
    --desired "${EXAMPLE}/desired.yaml" \
    --stage "${STAGE}" \
    --observed "${ARTIFACTS}/work/observed-latest.json" \
    --manifest "${EXAMPLE}/twin.yaml" \
    --out "${ARTIFACTS}/out/drift" \
    --sarif "${ARTIFACTS}/out/drift-report.sarif" || true
fi

curl -fsS "${BASE}/api/audit?limit=50" >"${ARTIFACTS}/out/audit.json" || echo '{"items":[]}' >"${ARTIFACTS}/out/audit.json"
curl -fsS "${BASE}/api/timeline?limit=100" >"${ARTIFACTS}/out/timeline.json"
cp -f "${ARTIFACTS}/db/twinops.sqlite" "${ARTIFACTS}/out/twinops.sqlite"

echo "==> Incident replay --verify"
# Use healthy baseline so narrative steps drive transitions; final expects SYNCED.
HEALTHY_OBS="${ARTIFACTS}/out/observed-baseline.json"
"${PYTHON}" -c "
import json
from pathlib import Path
base = json.loads(Path('${EXAMPLE}/telemetry.json').read_text())
for item in base.get('observations') or []:
    if item.get('prim') == '/World/Factory/LineA/Robot01':
        item['attributes'] = {
            'twinops:temperature': 42.0,
            'twinops:status': 'running',
            'twinops:firmware': '4.14',
        }
Path('${HEALTHY_OBS}').write_text(json.dumps(base, indent=2) + '\n')
"

# Deterministic fixture replay (RECOVERED + critical=0).
"${TWINOPSCTL}" incident replay \
  "${EXAMPLE}/incident-heat-spike.json" \
  --desired "${EXAMPLE}/desired.yaml" \
  --stage "${STAGE}" \
  --observed "${HEALTHY_OBS}" \
  --manifest "${EXAMPLE}/twin.yaml" \
  --verify --json >"${ARTIFACTS}/out/replay-verify.json"

echo "==> Persistence smoke (restart reads SQLite)"
cleanup
trap - EXIT
"${TWINOPSCTL}" serve \
  --example "${EXAMPLE}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --work-dir "${ARTIFACTS}/work" \
  --db "${ARTIFACTS}/db/twinops.sqlite" \
  --interval 2.0 \
  >"${LOG}.restart" 2>&1 &
SERVER_PID=$!
trap cleanup EXIT
for _ in $(seq 1 40); do
  curl -fsS "${BASE}/api/health" >/dev/null 2>&1 && break
  sleep 0.25
done
curl -fsS "${BASE}/api/timeline?limit=5" >"${ARTIFACTS}/out/timeline-after-restart.json"
"${PYTHON}" -c "
import json
from pathlib import Path
items = json.loads(Path('${ARTIFACTS}/out/timeline-after-restart.json').read_text()).get('items') or []
if not items:
    raise SystemExit('expected persisted timeline after restart')
print(f'    persisted timeline events={len(items)}')
"

# Required artifacts
for f in \
  plm-catalog.json \
  scene.json \
  scene.html \
  drift.html \
  incident.json \
  reconcile.json \
  replay-verify.json \
  twinops.sqlite \
  highlight-overlay.usda
do
  test -f "${ARTIFACTS}/out/${f}" || { echo "missing artifact: ${f}"; exit 1; }
done

cat <<EOF

portfolio-demo OK

  artifacts: ${ARTIFACTS}/out
  sqlite:    ${ARTIFACTS}/out/twinops.sqlite
  incident:  ${ARTIFACTS}/out/incident.json
  replay:    ${ARTIFACTS}/out/replay-verify.json
  apply:     exit=${APPLY_CODE} (see apply-verify.json; may be 1 if overlay empty)

EOF
