#!/usr/bin/env bash
# Job-mode E2E: isolated build Job keyed by input digest.
# Flow: helm install → DigitalTwin mode=job → Job succeeds → update input CM → NEW Job → new output digest.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CLUSTER_NAME="${TWINOPS_KIND_CLUSTER:-twinops-job-e2e}"
NAMESPACE="${TWINOPS_NAMESPACE:-twinops-system}"
IMAGE="${TWINOPS_OPERATOR_IMAGE:-twinops-operator:job-e2e}"
CM_NAME="assembly-line-inputs"
RELEASE="twinops-job-e2e"
TWIN="assembly-line-a"

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

IMG_REPO="${IMAGE%:*}"
IMG_TAG="${IMAGE##*:}"
if [[ "${IMG_REPO}" == "${IMAGE}" ]]; then
  IMG_TAG="latest"
fi

echo "==> Helm install operator"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install "${RELEASE}" deploy/helm/twinops-operator \
  --namespace "${NAMESPACE}" \
  --set createNamespace=false \
  --set image.repository="${IMG_REPO}" \
  --set image.tag="${IMG_TAG}" \
  --set image.pullPolicy=Never \
  --set buildImage="${IMAGE}" \
  --wait --timeout 240s

kubectl -n "${NAMESPACE}" rollout status deploy/twinops-controller-manager --timeout=120s

BUNDLE="${ROOT}/usd/generated/operator-job-e2e-bundle"
rm -rf "${BUNDLE}"
mkdir -p "${BUNDLE}"
sed 's|baseStage: assets/root.usda|baseStage: root.usda|' \
  "${ROOT}/examples/assembly-line/twin.yaml" >"${BUNDLE}/twin.yaml"
cp "${ROOT}/examples/assembly-line/assets/root.usda" "${BUNDLE}/root.usda"
cp "${ROOT}/examples/assembly-line/desired.yaml" "${BUNDLE}/desired.yaml"
cp "${ROOT}/examples/assembly-line/telemetry.json" "${BUNDLE}/telemetry.json"

kubectl -n "$NAMESPACE" delete digitaltwin "$TWIN" --ignore-not-found
kubectl -n "$NAMESPACE" delete job -l twinops.io/twin="$TWIN" --ignore-not-found
kubectl -n "$NAMESPACE" delete configmap "$CM_NAME" --ignore-not-found
kubectl -n "$NAMESPACE" delete configmap -l twinops.io/twin="$TWIN" --ignore-not-found

kubectl -n "$NAMESPACE" create configmap "$CM_NAME" \
  --from-file=twin.yaml="${BUNDLE}/twin.yaml" \
  --from-file=root.usda="${BUNDLE}/root.usda" \
  --from-file=desired.yaml="${BUNDLE}/desired.yaml" \
  --from-file=telemetry.json="${BUNDLE}/telemetry.json"

cat <<EOF | kubectl apply -f -
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: ${TWIN}
  namespace: ${NAMESPACE}
spec:
  artifactSource:
    configMapName: ${CM_NAME}
  intervalSeconds: 8
  build:
    mode: job
    activeDeadlineSeconds: 240
  outputPublish:
    mode: configmap
    keepRevisions: 5
EOF

wait_phase() {
  for _ in $(seq 1 150); do
    phase="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
    build_phase="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o jsonpath='{.status.build.phase}' 2>/dev/null || true)"
    if [[ "$phase" == "Ready" || "$phase" == "DriftDetected" ]]; then
      echo "$phase"
      return 0
    fi
    if [[ "$phase" == "Error" ]]; then
      kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o yaml | tail -60 >&2
      kubectl -n "$NAMESPACE" get jobs -l twinops.io/twin="$TWIN" -o wide >&2 || true
      kubectl -n "$NAMESPACE" logs deploy/twinops-controller-manager --tail=100 >&2 || true
      return 1
    fi
    sleep 2
  done
  echo "timeout phase=${phase:-none} build=${build_phase:-none}" >&2
  kubectl -n "$NAMESPACE" get jobs,pods,cm -l twinops.io/twin="$TWIN" -o wide >&2 || true
  kubectl -n "$NAMESPACE" logs deploy/twinops-controller-manager --tail=100 >&2 || true
  return 1
}

echo -n "==> Wait first job compose "
PHASE="$(wait_phase)"
echo "${PHASE}"

JOB1="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o jsonpath='{.status.build.jobName}')"
DIGEST1="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o jsonpath='{.status.inputDigest}')"
OUT1="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o jsonpath='{.status.output.digest}')"
if [[ -z "${JOB1}" ]]; then
  # Fallback: discover Job by label if status field lagged.
  JOB1="$(kubectl -n "$NAMESPACE" get jobs -l twinops.io/twin="$TWIN" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
fi
if [[ -z "${JOB1}" || -z "${DIGEST1}" || -z "${OUT1}" ]]; then
  echo "error: missing status fields jobName='${JOB1}' inputDigest='${DIGEST1}' output.digest='${OUT1}'" >&2
  kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o yaml | tail -80 >&2
  kubectl -n "$NAMESPACE" get jobs -l twinops.io/twin="$TWIN" -o wide >&2 || true
  exit 1
fi
echo "    jobName=${JOB1}"
echo "    inputDigest=${DIGEST1}"
echo "    output.digest=${OUT1}"

# Job name must contain digest key, not only generation number.
DIGEST_KEY="$(echo "${DIGEST1}" | sed 's|^sha256:||I' | tr 'A-F' 'a-f' | cut -c1-12)"
if [[ "${JOB1}" != *"${DIGEST_KEY}"* ]]; then
  echo "error: job name ${JOB1} does not include input digest key ${DIGEST_KEY}" >&2
  exit 1
fi

echo "==> Update input ConfigMap (drop desired.yaml → new digest)"
kubectl -n "$NAMESPACE" create configmap "$CM_NAME" \
  --from-file=twin.yaml="${BUNDLE}/twin.yaml" \
  --from-file=root.usda="${BUNDLE}/root.usda" \
  --from-file=telemetry.json="${BUNDLE}/telemetry.json" \
  --dry-run=client -o yaml | kubectl replace -f -

echo -n "==> Wait new Job + new output "
JOB2=""
DIGEST2=""
OUT2=""
for _ in $(seq 1 150); do
  DIGEST2="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o jsonpath='{.status.inputDigest}' 2>/dev/null || true)"
  JOB2="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o jsonpath='{.status.build.jobName}' 2>/dev/null || true)"
  OUT2="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o jsonpath='{.status.output.digest}' 2>/dev/null || true)"
  phase="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  if [[ -n "${DIGEST2}" && "${DIGEST2}" != "${DIGEST1}" && -n "${JOB2}" && "${JOB2}" != "${JOB1}" && -n "${OUT2}" && ( "$phase" == "Ready" || "$phase" == "DriftDetected" ) ]]; then
    echo "ok"
    break
  fi
  sleep 2
done

if [[ -z "${DIGEST2}" || "${DIGEST2}" == "${DIGEST1}" ]]; then
  echo "error: input digest did not change" >&2
  exit 1
fi
if [[ -z "${JOB2}" || "${JOB2}" == "${JOB1}" ]]; then
  echo "error: expected a NEW Job after input change (old=${JOB1} new=${JOB2})" >&2
  kubectl -n "$NAMESPACE" get jobs -l twinops.io/twin="$TWIN" -o wide >&2 || true
  kubectl -n "$NAMESPACE" get digitaltwin "$TWIN" -o yaml | tail -80 >&2
  exit 1
fi
echo "    jobName=${JOB2} (was ${JOB1})"
echo "    inputDigest=${DIGEST2}"
echo "    output.digest=${OUT2}"

# Result CMs should exist for both digests (or at least the new one).
kubectl -n "$NAMESPACE" get configmap -l twinops.io/build-result=true,twinops.io/twin="$TWIN" -o name | grep -q .

echo "operator-job-e2e OK (new Job after input CM change)"
