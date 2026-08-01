#!/usr/bin/env bash
# In-cluster operator E2E: build image → kind load → helm install → CR → digest → restart.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CLUSTER_NAME="${TWINOPS_KIND_CLUSTER:-twinops-incluster}"
NAMESPACE="${TWINOPS_NAMESPACE:-twinops-system}"
IMAGE="${TWINOPS_OPERATOR_IMAGE:-twinops-operator:incluster-e2e}"
CM_NAME="assembly-line-inputs"
RELEASE="twinops-op-e2e"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need kubectl
need docker
need helm
need kind

if [[ ! -x "${ROOT}/.venv/bin/twinopsctl" ]]; then
  make install
fi

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "==> Creating kind cluster ${CLUSTER_NAME}"
  kind create cluster --name "$CLUSTER_NAME"
fi
kubectl config use-context "kind-${CLUSTER_NAME}" >/dev/null
kubectl wait --for=condition=Ready node --all --timeout=120s >/dev/null

echo "==> Build operator image ${IMAGE}"
docker build -f Dockerfile.operator -t "${IMAGE}" .

echo "==> kind load ${IMAGE}"
kind load docker-image "${IMAGE}" --name "$CLUSTER_NAME"

# Split repository:tag for helm
IMG_REPO="${IMAGE%:*}"
IMG_TAG="${IMAGE##*:}"
if [[ "${IMG_REPO}" == "${IMAGE}" ]]; then
  IMG_TAG="latest"
fi

echo "==> Helm install operator (in-cluster)"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install "${RELEASE}" deploy/helm/twinops-operator \
  --namespace "${NAMESPACE}" \
  --set createNamespace=false \
  --set image.repository="${IMG_REPO}" \
  --set image.tag="${IMG_TAG}" \
  --set image.pullPolicy=Never \
  --set artifactAllowPrivate=0 \
  --wait --timeout 180s

kubectl -n "${NAMESPACE}" rollout status deploy/twinops-controller-manager --timeout=120s

echo "==> Prepare ConfigMap artifact bundle"
BUNDLE="${ROOT}/usd/generated/operator-incluster-e2e-bundle"
rm -rf "${BUNDLE}"
mkdir -p "${BUNDLE}"
sed 's|baseStage: assets/root.usda|baseStage: root.usda|' \
  "${ROOT}/examples/assembly-line/twin.yaml" >"${BUNDLE}/twin.yaml"
cp "${ROOT}/examples/assembly-line/assets/root.usda" "${BUNDLE}/root.usda"
cp "${ROOT}/examples/assembly-line/desired.yaml" "${BUNDLE}/desired.yaml"
cp "${ROOT}/examples/assembly-line/telemetry.json" "${BUNDLE}/telemetry.json"

kubectl -n "$NAMESPACE" delete digitaltwin assembly-line-a --ignore-not-found
kubectl -n "$NAMESPACE" delete configmap "$CM_NAME" assembly-line-a-output --ignore-not-found
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
EOF

wait_phase() {
  for _ in $(seq 1 120); do
    phase="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.phase}' 2>/dev/null || true)"
    if [[ "$phase" == "Ready" || "$phase" == "DriftDetected" ]]; then
      echo "$phase"
      return 0
    fi
    if [[ "$phase" == "Error" ]]; then
      kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o yaml | tail -50 >&2
      kubectl -n "$NAMESPACE" logs deploy/twinops-controller-manager --tail=80 >&2 || true
      return 1
    fi
    sleep 2
  done
  echo "timeout phase=${phase:-none}" >&2
  kubectl -n "$NAMESPACE" logs deploy/twinops-controller-manager --tail=80 >&2 || true
  return 1
}

echo -n "==> Wait first reconcile "
PHASE="$(wait_phase)"
echo "${PHASE}"

DIGEST1="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.inputDigest}')"
if [[ -z "${DIGEST1}" ]]; then
  DIGEST1="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.artifactDigest}')"
fi
OUT1="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.uri}')"
OUT_DIGEST1="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.digest}')"
OUT_REV1="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.revision}')"
test -n "${DIGEST1}"
test -n "${OUT1}"
test -n "${OUT_DIGEST1}"
echo "    inputDigest=${DIGEST1}"
echo "    output.uri=${OUT1}"
echo "    output.digest=${OUT_DIGEST1}"
echo "    output.revision=${OUT_REV1}"
kubectl -n "$NAMESPACE" get configmap assembly-line-a-output >/dev/null

extract_and_validate_bundle() {
  local extract
  extract="$(mktemp -d)"
  kubectl -n "$NAMESPACE" get configmap assembly-line-a-output -o jsonpath='{.binaryData.bundle\.tar\.gz}' \
    | base64 -d >"${extract}/bundle.tar.gz"
  mkdir -p "${extract}/out"
  tar -xzf "${extract}/bundle.tar.gz" -C "${extract}/out"
  test -f "${extract}/out/root.usda"
  test -f "${extract}/out/assets/root.usda"
  if [[ -f "${extract}/out/reconciliation-report.json" ]]; then
    echo "error: report must not be in durable bundle" >&2
    rm -rf "${extract}"
    return 1
  fi
  if python3 -c "import pxr" 2>/dev/null; then
    python3 "${ROOT}/scripts/validate_usd.py" "${extract}/out/root.usda" --json
  elif [[ -x "${ROOT}/.venv/bin/python" ]] && "${ROOT}/.venv/bin/python" -c "import pxr" 2>/dev/null; then
    "${ROOT}/.venv/bin/python" "${ROOT}/scripts/validate_usd.py" "${extract}/out/root.usda" --json
  else
    echo "    (pxr not installed — structural checks only)"
  fi
  rm -rf "${extract}"
}

echo "==> Validate published bundle (assets + root)"
extract_and_validate_bundle

echo "==> Update ConfigMap (drop desired.yaml)"
kubectl -n "$NAMESPACE" create configmap "$CM_NAME" \
  --from-file=twin.yaml="${BUNDLE}/twin.yaml" \
  --from-file=root.usda="${BUNDLE}/root.usda" \
  --from-file=telemetry.json="${BUNDLE}/telemetry.json" \
  --dry-run=client -o yaml | kubectl replace -f -

echo -n "==> Wait input digest change "
DIGEST2=""
for _ in $(seq 1 90); do
  DIGEST2="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.inputDigest}' 2>/dev/null || true)"
  if [[ -z "${DIGEST2}" ]]; then
    DIGEST2="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.artifactDigest}' 2>/dev/null || true)"
  fi
  if [[ -n "${DIGEST2}" && "${DIGEST2}" != "${DIGEST1}" ]]; then
    echo "${DIGEST2}"
    break
  fi
  sleep 2
done
test -n "${DIGEST2}"
test "${DIGEST2}" != "${DIGEST1}"

OUT_DIGEST2="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.digest}')"
OUT_REV2="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.revision}')"
test -n "${OUT_DIGEST2}"
echo "    output.digest=${OUT_DIGEST2} rev=${OUT_REV2}"

echo "==> Restart operator Pod (recovery + digest stability)"
kubectl -n "$NAMESPACE" delete pod -l app.kubernetes.io/name=twinops-operator --wait=true
kubectl -n "$NAMESPACE" rollout status deploy/twinops-controller-manager --timeout=120s

echo -n "==> Wait post-restart healthy phase "
PHASE2="$(wait_phase)"
echo "${PHASE2}"
DIGEST3="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.inputDigest}')"
if [[ -z "${DIGEST3}" ]]; then
  DIGEST3="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.artifactDigest}')"
fi
OUT_DIGEST3="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.digest}')"
OUT_REV3="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.revision}')"
test "${DIGEST3}" = "${DIGEST2}"
test "${OUT_DIGEST3}" = "${OUT_DIGEST2}"
test "${OUT_REV3}" = "${OUT_REV2}"
OUT3="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.uri}')"
test -n "${OUT3}"
echo "    inputDigest stable=${DIGEST3}"
echo "    output.digest stable=${OUT_DIGEST3} rev=${OUT_REV3}"
extract_and_validate_bundle

echo "operator-incluster-e2e OK (phase=${PHASE2}, digests stable after restart, bundle valid)"
