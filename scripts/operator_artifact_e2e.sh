#!/usr/bin/env bash
# Kubernetes E2E: ConfigMap artifactSource → reconcile → digest → ConfigMap update.
# Uses out-of-cluster manager (same pattern as operator_kind_demo) so CI needs no image push.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CLUSTER_NAME="${TWINOPS_KIND_CLUSTER:-twinops-e2e}"
NAMESPACE="${TWINOPS_NAMESPACE:-twinops-system}"
PROVIDER="${TWINOPS_CLUSTER_PROVIDER:-auto}"
MANAGER_LOG="${TMPDIR:-/tmp}/twinops-operator-artifact-e2e.log"
CM_NAME="assembly-line-inputs"

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

echo "==> Apply CRD + namespace"
kubectl apply -f deploy/helm/twinops-operator/crds/twinops.io_digitaltwins.yaml
kubectl apply -f config/samples/namespace.yaml

echo "==> Create ConfigMap artifact"
kubectl -n "$NAMESPACE" delete configmap "$CM_NAME" --ignore-not-found
kubectl -n "$NAMESPACE" create configmap "$CM_NAME" \
  --from-file=twin.yaml="${ROOT}/examples/assembly-line/twin.yaml" \
  --from-file=desired.yaml="${ROOT}/examples/assembly-line/desired.yaml" \
  --from-file=telemetry.json="${ROOT}/examples/assembly-line/telemetry.json"

cat <<EOF | kubectl apply -f -
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: assembly-line-a
  namespace: ${NAMESPACE}
spec:
  artifactSource:
    configMapName: ${CM_NAME}
  outputDir: ${ROOT}/usd/generated/operator-artifact-e2e
  intervalSeconds: 10
  twinopsctl: ${ROOT}/.venv/bin/twinopsctl
EOF

echo "==> Start out-of-cluster manager"
: >"${MANAGER_LOG}"
./bin/manager \
  --metrics-bind-address=:18082 \
  --health-probe-bind-address=:18083 \
  --twinopsctl="${ROOT}/.venv/bin/twinopsctl" \
  >"${MANAGER_LOG}" 2>&1 &
MANAGER_PID=$!
cleanup() {
  kill "${MANAGER_PID}" 2>/dev/null || true
  wait "${MANAGER_PID}" 2>/dev/null || true
}
trap cleanup EXIT

wait_phase() {
  local want="$1"
  for _ in $(seq 1 90); do
    phase="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.phase}' 2>/dev/null || true)"
    if [[ "$phase" == "Ready" || "$phase" == "DriftDetected" ]]; then
      if [[ -z "$want" || "$phase" == "$want" || "$want" == "any-ok" ]]; then
        echo "$phase"
        return 0
      fi
    fi
    if [[ "$phase" == "Error" ]]; then
      echo "Error" >&2
      kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o yaml | tail -40 >&2
      tail -n 80 "${MANAGER_LOG}" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "timeout phase=${phase:-none}" >&2
  tail -n 80 "${MANAGER_LOG}" >&2 || true
  return 1
}

echo -n "==> Wait reconcile "
PHASE="$(wait_phase any-ok)"
echo "${PHASE}"

DIGEST1="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.artifactDigest}')"
STAGE="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.stagePath}')"
test -n "${DIGEST1}"
test -n "${STAGE}"
test -f "${STAGE}"
echo "    digest1=${DIGEST1}"
echo "    stage=${STAGE}"

echo "==> Update ConfigMap (remove desired.yaml to prove atomic replace)"
kubectl -n "$NAMESPACE" create configmap "$CM_NAME" \
  --from-file=twin.yaml="${ROOT}/examples/assembly-line/twin.yaml" \
  --from-file=telemetry.json="${ROOT}/examples/assembly-line/telemetry.json" \
  --dry-run=client -o yaml | kubectl apply -f -

echo -n "==> Wait digest change "
DIGEST2=""
for _ in $(seq 1 90); do
  DIGEST2="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.artifactDigest}' 2>/dev/null || true)"
  if [[ -n "${DIGEST2}" && "${DIGEST2}" != "${DIGEST1}" ]]; then
    echo "${DIGEST2}"
    break
  fi
  sleep 1
done
test -n "${DIGEST2}"
test "${DIGEST2}" != "${DIGEST1}"

WORKSPACE="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.workspacePath}')"
if [[ -f "${WORKSPACE}/desired.yaml" ]]; then
  echo "error: stale desired.yaml present after ConfigMap update" >&2
  exit 1
fi

echo "operator-artifact-e2e OK (phase=${PHASE}, digests changed, stale file gone)"
