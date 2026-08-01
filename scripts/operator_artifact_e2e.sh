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

echo "==> Create ConfigMap artifact (self-contained bundle)"
BUNDLE="${ROOT}/usd/generated/operator-artifact-e2e-bundle"
rm -rf "${BUNDLE}"
mkdir -p "${BUNDLE}"
# baseStage must live next to twin.yaml inside the materialized workspace.
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
  name: assembly-line-a
  namespace: ${NAMESPACE}
spec:
  artifactSource:
    configMapName: ${CM_NAME}
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
# kubectl apply three-way merge keeps keys absent from the new manifest when the
# ConfigMap was created without last-applied-configuration. replace fully swaps .data.
kubectl -n "$NAMESPACE" create configmap "$CM_NAME" \
  --from-file=twin.yaml="${BUNDLE}/twin.yaml" \
  --from-file=root.usda="${BUNDLE}/root.usda" \
  --from-file=telemetry.json="${BUNDLE}/telemetry.json" \
  --dry-run=client -o yaml | kubectl replace -f -

# Confirm the API object actually dropped desired.yaml before waiting on status.
CM_KEYS="$(kubectl -n "$NAMESPACE" get configmap "$CM_NAME" -o jsonpath='{.data}' 2>/dev/null || true)"
if echo "${CM_KEYS}" | grep -q 'desired.yaml'; then
  echo "error: ConfigMap still has desired.yaml after replace" >&2
  kubectl -n "$NAMESPACE" get configmap "$CM_NAME" -o yaml >&2 || true
  exit 1
fi

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
if [[ -z "${DIGEST2}" || "${DIGEST2}" == "${DIGEST1}" ]]; then
  echo "timeout digest1=${DIGEST1} digest2=${DIGEST2:-none}" >&2
  kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o yaml | tail -50 >&2 || true
  tail -n 80 "${MANAGER_LOG}" >&2 || true
  exit 1
fi
test -n "${DIGEST2}"
test "${DIGEST2}" != "${DIGEST1}"

WORKSPACE="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.workspacePath}')"
if [[ -f "${WORKSPACE}/desired.yaml" ]]; then
  echo "error: stale desired.yaml present after ConfigMap update" >&2
  exit 1
fi

OUT_URI="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.uri}')"
OUT_DIGEST="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.digest}')"
BUNDLE_KEY="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.bundleKey}')"
test -n "${OUT_URI}"
test -n "${OUT_DIGEST}"
test "${BUNDLE_KEY}" = "bundle.tar.gz"
echo "    output.uri=${OUT_URI}"
echo "    output.digest=${OUT_DIGEST}"
echo "    output.bundleKey=${BUNDLE_KEY}"
kubectl -n "$NAMESPACE" get configmap assembly-line-a-output -o jsonpath='{.metadata.annotations.twinops\.io/output-digest}' | grep -q .

echo "==> Extract + validate published bundle"
EXTRACT="$(mktemp -d)"
kubectl -n "$NAMESPACE" get configmap assembly-line-a-output -o jsonpath='{.binaryData.bundle\.tar\.gz}' \
  | base64 -d >"${EXTRACT}/bundle.tar.gz"
mkdir -p "${EXTRACT}/out"
tar -xzf "${EXTRACT}/bundle.tar.gz" -C "${EXTRACT}/out"
test -f "${EXTRACT}/out/root.usda"
test -f "${EXTRACT}/out/assets/root.usda"
# Must not ship volatile report in durable content bundle
if [[ -f "${EXTRACT}/out/reconciliation-report.json" ]]; then
  echo "error: reconciliation-report.json must not be in content bundle" >&2
  exit 1
fi
if python3 -c "import pxr" 2>/dev/null; then
  python3 "${ROOT}/scripts/validate_usd.py" "${EXTRACT}/out/root.usda" --json
elif [[ -x "${ROOT}/.venv/bin/python" ]] && "${ROOT}/.venv/bin/python" -c "import pxr" 2>/dev/null; then
  "${ROOT}/.venv/bin/python" "${ROOT}/scripts/validate_usd.py" "${EXTRACT}/out/root.usda" --json
else
  echo "    (pxr not installed — structural bundle checks only)"
fi
rm -rf "${EXTRACT}"

echo "operator-artifact-e2e OK (phase=${PHASE}, digests changed, bundle opens)"
