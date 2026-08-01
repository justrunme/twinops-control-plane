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
helm upgrade --install "${RELEASE}" deploy/helm/twinops-operator \
  --namespace "${NAMESPACE}" --create-namespace \
  --set image.repository="${IMG_REPO}" \
  --set image.tag="${IMG_TAG}" \
  --set image.pullPolicy=IfNotPresent \
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
  outputDir: /tmp/twinops/assembly-line-a
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
test -n "${DIGEST1}"
test -n "${OUT1}"
echo "    inputDigest=${DIGEST1}"
echo "    output.uri=${OUT1}"
kubectl -n "$NAMESPACE" get configmap assembly-line-a-output >/dev/null

echo "==> Update ConfigMap (drop desired.yaml)"
kubectl -n "$NAMESPACE" create configmap "$CM_NAME" \
  --from-file=twin.yaml="${BUNDLE}/twin.yaml" \
  --from-file=root.usda="${BUNDLE}/root.usda" \
  --from-file=telemetry.json="${BUNDLE}/telemetry.json" \
  --dry-run=client -o yaml | kubectl replace -f -

echo -n "==> Wait digest change "
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

OUT_DIGEST="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.digest}')"
test -n "${OUT_DIGEST}"

echo "==> Restart operator Pod (recovery)"
kubectl -n "$NAMESPACE" delete pod -l app.kubernetes.io/name=twinops-operator --wait=true
kubectl -n "$NAMESPACE" rollout status deploy/twinops-controller-manager --timeout=120s

echo -n "==> Wait post-restart healthy phase "
PHASE2="$(wait_phase)"
echo "${PHASE2}"
DIGEST3="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.inputDigest}')"
if [[ -z "${DIGEST3}" ]]; then
  DIGEST3="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.artifactDigest}')"
fi
test "${DIGEST3}" = "${DIGEST2}"
OUT3="$(kubectl -n "$NAMESPACE" get digitaltwin assembly-line-a -o jsonpath='{.status.output.uri}')"
test -n "${OUT3}"

echo "operator-incluster-e2e OK (phase=${PHASE2}, digest recovered, output=${OUT3})"
