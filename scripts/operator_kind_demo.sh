#!/usr/bin/env bash
# TwinOps DigitalTwin operator demo on a local cluster (k3d preferred, kind fallback).
#
# Usage:
#   ./scripts/operator_kind_demo.sh           # create/reuse cluster, apply CR, reconcile
#   ./scripts/operator_kind_demo.sh --once    # same, exit after first successful status
#   ./scripts/operator_kind_demo.sh --cleanup # delete local demo cluster
#
# Env:
#   TWINOPS_CLUSTER_PROVIDER=k3d|kind|auto  (default: auto → k3d if available, else kind)
#   TWINOPS_KIND_CLUSTER=twinops            cluster name
#   TWINOPS_NAMESPACE=twinops-system
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CLUSTER_NAME="${TWINOPS_KIND_CLUSTER:-twinops}"
NAMESPACE="${TWINOPS_NAMESPACE:-twinops-system}"
PROVIDER="${TWINOPS_CLUSTER_PROVIDER:-auto}"
SAMPLE_OUT="${ROOT}/usd/generated/operator-demo/digitaltwin.yaml"
MANAGER_LOG="${TWINOPS_OPERATOR_LOG:-/tmp/twinops-operator-demo.log}"
CLEANUP=0
ONCE=0

for arg in "$@"; do
  case "$arg" in
    --cleanup) CLEANUP=1 ;;
    --once) ONCE=1 ;;
    -h|--help)
      sed -n '2,13p' "$0"
      exit 0
      ;;
  esac
done

resolve_provider() {
  case "$PROVIDER" in
    k3d|kind) echo "$PROVIDER" ;;
    auto)
      if command -v k3d >/dev/null 2>&1; then
        echo k3d
      elif command -v kind >/dev/null 2>&1; then
        echo kind
      else
        echo "missing required command: k3d or kind" >&2
        exit 1
      fi
      ;;
    *)
      echo "unsupported TWINOPS_CLUSTER_PROVIDER=${PROVIDER} (use k3d|kind|auto)" >&2
      exit 1
      ;;
  esac
}

PROVIDER="$(resolve_provider)"

if [[ "$CLEANUP" -eq 1 ]]; then
  if command -v k3d >/dev/null 2>&1; then
    k3d cluster delete "$CLUSTER_NAME" 2>/dev/null || true
  fi
  if command -v kind >/dev/null 2>&1; then
    kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || true
  fi
  echo "Deleted local demo cluster '${CLUSTER_NAME}' (k3d/kind)"
  exit 0
fi

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 1
  }
}

need kubectl
need docker
need "$PROVIDER"
docker info >/dev/null 2>&1 || {
  echo "Docker is not running. Start Docker Desktop and retry." >&2
  exit 1
}

cluster_exists() {
  if [[ "$PROVIDER" == "k3d" ]]; then
    k3d cluster list -o json 2>/dev/null | grep -q "\"name\":\"${CLUSTER_NAME}\""
  else
    kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"
  fi
}

ensure_cluster() {
  if cluster_exists; then
    echo "==> Reusing ${PROVIDER} cluster '${CLUSTER_NAME}'"
  else
    echo "==> Creating ${PROVIDER} cluster '${CLUSTER_NAME}'"
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
}

if [[ ! -x "$ROOT/.venv/bin/twinopsctl" ]]; then
  echo "==> Installing Python toolkit"
  make install
fi

echo "==> Building operator manager"
make operator-build

ensure_cluster
kubectl wait --for=condition=Ready node --all --timeout=120s >/dev/null

echo "==> Applying CRD / namespace / sample"
kubectl apply -f config/crd/bases/twinops.io_digitaltwins.yaml
kubectl apply -f config/samples/namespace.yaml

mkdir -p "$(dirname "$SAMPLE_OUT")"
cat >"$SAMPLE_OUT" <<EOF
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: assembly-line-a
  namespace: ${NAMESPACE}
spec:
  manifestPath: ${ROOT}/examples/assembly-line/twin.yaml
  desiredPath: ${ROOT}/examples/assembly-line/desired.yaml
  observedPath: ${ROOT}/examples/assembly-line/telemetry.json
  outputDir: ${ROOT}/usd/generated/operator-demo/stage
  intervalSeconds: 15
  twinopsctl: ${ROOT}/.venv/bin/twinopsctl
EOF

kubectl apply -f "$SAMPLE_OUT"

echo "==> Starting out-of-cluster manager"
if [[ -f "$MANAGER_LOG" ]]; then
  : >"$MANAGER_LOG"
fi

./bin/manager \
  --metrics-bind-address=:18080 \
  --health-probe-bind-address=:18081 \
  --twinopsctl="${ROOT}/.venv/bin/twinopsctl" \
  >"$MANAGER_LOG" 2>&1 &
MANAGER_PID=$!

cleanup() {
  if kill -0 "$MANAGER_PID" 2>/dev/null; then
    kill "$MANAGER_PID" 2>/dev/null || true
    wait "$MANAGER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo -n "==> Waiting for DigitalTwin status"
PHASE=""
for _ in $(seq 1 60); do
  PHASE="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  if [[ "$PHASE" == "Ready" || "$PHASE" == "DriftDetected" || "$PHASE" == "Error" ]]; then
    echo " ${PHASE}"
    break
  fi
  echo -n "."
  sleep 1
done

if [[ -z "$PHASE" ]]; then
  echo
  echo "Timed out waiting for status. Manager log:"
  tail -n 80 "$MANAGER_LOG" || true
  exit 1
fi

echo
kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o wide
echo
kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.message}{"\n"}'
echo "Drift: $(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.drift.status}')"
echo "Stage: $(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.stagePath}')"
echo
echo "Provider:    ${PROVIDER}"
echo "Manager log: $MANAGER_LOG"
echo "Sample CR:   $SAMPLE_OUT"
echo
echo "Useful commands:"
echo "  kubectl -n ${NAMESPACE} get dtwin"
echo "  kubectl -n ${NAMESPACE} describe dtwin assembly-line-a"
echo "  make operator-demo-cleanup"
echo
if [[ "$PHASE" == "Error" ]]; then
  echo "Operator reported Error — showing manager log tail:"
  tail -n 80 "$MANAGER_LOG" || true
  exit 1
fi

echo "Operator demo succeeded (phase=${PHASE})."
if [[ "$ONCE" -eq 1 ]]; then
  exit 0
fi
echo "Press Ctrl+C to stop the manager (cluster is kept)."
wait "$MANAGER_PID"
