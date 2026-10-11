#!/usr/bin/env bash
# Kind E2E: REST PLM revision change → automatic new immutable USD output revision.
# Also asserts outage→recovery resyncs exactly once.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CLUSTER_NAME="${TWINOPS_KIND_CLUSTER:-twinops-plm-e2e}"
NAMESPACE="${TWINOPS_NAMESPACE:-twinops-system}"
PROVIDER="${TWINOPS_CLUSTER_PROVIDER:-auto}"
MANAGER_LOG="${TMPDIR:-/tmp}/twinops-operator-plm-e2e.log"
PLM_LOG="${TMPDIR:-/tmp}/twinops-mock-plm.log"
CM_NAME="assembly-line-plm-inputs"
OUT_DIR="${TWINOPS_PLM_E2E_OUT:-/tmp/twinops-plm-e2e}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need kubectl
need docker

resolve_provider() {
  case "$PROVIDER" in
    k3d|kind) echo "$PROVIDER" ;;
    auto)
      if command -v kind >/dev/null 2>&1; then echo kind
      elif command -v k3d >/dev/null 2>&1; then echo k3d
      else echo "need kind or k3d" >&2; exit 1
      fi ;;
    *) echo "bad provider" >&2; exit 1 ;;
  esac
}
PROVIDER="$(resolve_provider)"
need "$PROVIDER"

if [[ ! -x "${ROOT}/.venv/bin/twinopsctl" ]]; then
  make install
fi
make operator-build
PYTHON="${ROOT}/.venv/bin/python"
mkdir -p "$OUT_DIR"

cluster_exists() {
  if [[ "$PROVIDER" == "k3d" ]]; then
    k3d cluster list -o json 2>/dev/null | grep -q "\"name\":\"${CLUSTER_NAME}\""
  else
    kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"
  fi
}

if ! cluster_exists; then
  echo "==> Creating ${PROVIDER} cluster ${CLUSTER_NAME}"
  if [[ "$PROVIDER" == "k3d" ]]; then
    k3d cluster create "$CLUSTER_NAME" --agents 0 --wait
  else
    kind create cluster --name "$CLUSTER_NAME"
  fi
fi
if [[ "$PROVIDER" == "k3d" ]]; then
  kubectl config use-context "k3d-${CLUSTER_NAME}" >/dev/null
else
  kubectl config use-context "kind-${CLUSTER_NAME}" >/dev/null
fi
kubectl wait --for=condition=Ready node --all --timeout=120s >/dev/null

echo "==> Start mock PLM HTTP server"
: >"${PLM_LOG}"
PLM_META="$OUT_DIR/plm-meta.json"
PLM_CTRL="$OUT_DIR/plm-control.json"
"$PYTHON" "${ROOT}/scripts/run_mock_plm.py" \
  --catalog "${ROOT}/examples/assembly-line/plm-catalog.json" \
  --token plm-e2e-token \
  --meta-out "$PLM_META" \
  --control "$PLM_CTRL" \
  >"${PLM_LOG}" 2>&1 &
PLM_PID=$!

# Wait for meta file with URL
for _ in $(seq 1 50); do
  if [[ -s "$PLM_META" ]] && grep -q '"url"' "$PLM_META"; then
    break
  fi
  sleep 0.1
done
PLM_URL="$(python3 -c "import json; print(json.load(open('$PLM_META'))['url'])")"
echo "PLM URL: $PLM_URL"

cleanup() {
  echo '{"cmd":"stop"}' >"${PLM_CTRL:-$OUT_DIR/plm-control.json}" 2>/dev/null || true
  kill "${MANAGER_PID:-}" 2>/dev/null || true
  kill "${PLM_PID:-}" 2>/dev/null || true
  wait "${MANAGER_PID:-}" 2>/dev/null || true
  wait "${PLM_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT

echo "==> Apply CRD + namespace"
kubectl apply -f deploy/helm/twinops-operator/crds/twinops.io_digitaltwins.yaml
kubectl apply -f config/samples/namespace.yaml

echo "==> Create PLM token secret + ConfigMap artifact"
kubectl -n "$NAMESPACE" delete secret plm-token --ignore-not-found
kubectl -n "$NAMESPACE" create secret generic plm-token --from-literal=token=plm-e2e-token

BUNDLE="${OUT_DIR}/bundle"
rm -rf "${BUNDLE}"
mkdir -p "${BUNDLE}"
sed 's|baseStage: assets/root.usda|baseStage: root.usda|' \
  "${ROOT}/examples/assembly-line/twin.yaml" >"${BUNDLE}/twin.yaml"
cp "${ROOT}/examples/assembly-line/assets/root.usda" "${BUNDLE}/root.usda"
cp "${ROOT}/examples/assembly-line/desired.yaml" "${BUNDLE}/desired.yaml"
cp "${ROOT}/examples/assembly-line/telemetry.json" "${BUNDLE}/telemetry.json"

kubectl -n "$NAMESPACE" delete configmap "$CM_NAME" --ignore-not-found
kubectl -n "$NAMESPACE" create configmap "$CM_NAME" \
  --from-file=twin.yaml="${BUNDLE}/twin.yaml" \
  --from-file=root.usda="${BUNDLE}/root.usda" \
  --from-file=desired.yaml="${BUNDLE}/desired.yaml" \
  --from-file=telemetry.json="${BUNDLE}/telemetry.json"

cat <<EOF | kubectl apply -f -
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: assembly-line-plm
  namespace: ${NAMESPACE}
spec:
  artifactSource:
    configMapName: ${CM_NAME}
  intervalSeconds: 5
  plm:
    url: ${PLM_URL}
    tokenSecretRef:
      name: plm-token
      key: token
    pollSeconds: 3
    syncManifest: true
  outputPublish:
    enabled: true
    mode: configmap
    keepRevisions: 5
EOF

echo "==> Start out-of-cluster manager"
: >"${MANAGER_LOG}"
./bin/manager \
  --metrics-bind-address=:18092 \
  --health-probe-bind-address=:18093 \
  --twinopsctl="${ROOT}/.venv/bin/twinopsctl" \
  >"${MANAGER_LOG}" 2>&1 &
MANAGER_PID=$!

wait_ready() {
  for _ in $(seq 1 90); do
    phase="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.phase}' 2>/dev/null || true)"
    rev="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.output.revision}' 2>/dev/null || true)"
    etag="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.plm.etag}' 2>/dev/null || true)"
    if [[ "$phase" == "Ready" || "$phase" == "DriftDetected" ]] && [[ -n "$rev" && "$rev" != "0" ]] && [[ -n "$etag" ]]; then
      echo "phase=$phase rev=$rev etag=$etag"
      return 0
    fi
    sleep 2
  done
  echo "timeout waiting for initial PLM sync" >&2
  kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o yaml >&2 || true
  tail -n 80 "$MANAGER_LOG" >&2 || true
  return 1
}

echo "==> Wait for initial compose + PLM sync"
wait_ready
REV1="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.output.revision}')"
FP1="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.plm.fingerprint}')"
echo "initial revision=$REV1 fingerprint=$FP1"

echo "==> Bump PLM revision (no manual twin edit)"
echo '{"cmd":"bump"}' >"$OUT_DIR/plm-control.json"

wait_rev() {
  local want_gt="$1"
  for _ in $(seq 1 60); do
    rev="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.output.revision}' 2>/dev/null || true)"
    if [[ -n "$rev" && "$rev" -gt "$want_gt" ]]; then
      echo "$rev"
      return 0
    fi
    sleep 2
  done
  return 1
}

REV2="$(wait_rev "$REV1")" || {
  echo "PLM bump did not produce new output revision" >&2
  kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o yaml >&2
  tail -n 100 "$MANAGER_LOG" >&2
  exit 1
}
echo "new revision after PLM bump: $REV2"
HIST="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.output.history}' )"
echo "$HIST" | tee "$OUT_DIR/history-after-bump.json"
python3 - <<PY
import json, os
hist = json.loads('''$HIST''' or '[]')
assert len(hist) >= 2, hist
revs = [h.get('revision') for h in hist]
assert max(revs) == int('$REV2'), revs
print('history ok', revs)
PY

echo "==> Simulate PLM outage then recovery (resync exactly once)"
RESYNC_BEFORE="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.plm.resyncCount}')"
RESYNC_BEFORE="${RESYNC_BEFORE:-0}"
echo '{"cmd":"outage"}' >"$OUT_DIR/plm-control.json"
# Wait until inOutage or consecutiveFailures grow
for _ in $(seq 1 30); do
  outage="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.plm.inOutage}' 2>/dev/null || true)"
  fails="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.plm.consecutiveFailures}' 2>/dev/null || true)"
  if [[ "$outage" == "true" || "${fails:-0}" -gt 0 ]]; then
    break
  fi
  sleep 2
done
echo '{"cmd":"recover"}' >"$OUT_DIR/plm-control.json"

for _ in $(seq 1 40); do
  resync="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.plm.resyncCount}' 2>/dev/null || true)"
  outage="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.plm.inOutage}' 2>/dev/null || true)"
  if [[ "${resync:-0}" -gt "$RESYNC_BEFORE" && "$outage" != "true" ]]; then
    echo "resyncCount=$resync (before=$RESYNC_BEFORE)"
    break
  fi
  sleep 2
done
RESYNC_AFTER="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.plm.resyncCount}')"
python3 - <<PY
before=int('$RESYNC_BEFORE' or 0)
after=int('$RESYNC_AFTER' or 0)
assert after == before + 1, (before, after)
print('resync exactly once OK')
PY

# Idle a bit and ensure no extra resync
sleep 8
RESYNC_FINAL="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o jsonpath='{.status.plm.resyncCount}')"
python3 - <<PY
after=int('$RESYNC_AFTER' or 0)
final=int('$RESYNC_FINAL' or 0)
assert final == after, (after, final)
print('no extra resync OK')
PY

kubectl -n "$NAMESPACE" get digitaltwin assembly-line-plm -o json >"$OUT_DIR/digitaltwin-final.json"
cat >"$OUT_DIR/plm-e2e-report.json" <<EOF
{
  "revisionBefore": ${REV1},
  "revisionAfterBump": ${REV2},
  "resyncBefore": ${RESYNC_BEFORE},
  "resyncAfter": ${RESYNC_AFTER},
  "resyncFinal": ${RESYNC_FINAL}
}
EOF
echo "operator_plm_e2e OK"
cat "$OUT_DIR/plm-e2e-report.json"
