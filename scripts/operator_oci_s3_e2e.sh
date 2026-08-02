#!/usr/bin/env bash
# OCI + S3 publish E2E with local registry and MinIO inside kind.
# Validates fail-closed tools are present and real push works (no ConfigMap fallback).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CLUSTER_NAME="${TWINOPS_KIND_CLUSTER:-twinops-oci-s3-e2e}"
NAMESPACE="${TWINOPS_NAMESPACE:-twinops-system}"
IMAGE="${TWINOPS_OPERATOR_IMAGE:-twinops-operator:oci-s3-e2e}"
CM_NAME="assembly-line-inputs"
RELEASE="twinops-oci-s3"
TWIN_OCI="assembly-line-oci"
TWIN_S3="assembly-line-s3"
REGISTRY_NS="registry"
MINIO_NS="minio"

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

# Assert oras + aws exist in the image (critical correctness).
echo "==> Verify oras + aws in image"
docker run --rm --entrypoint /bin/sh "${IMAGE}" -c 'oras version && aws --version'

echo "==> kind load ${IMAGE}"
kind load docker-image "${IMAGE}" --name "$CLUSTER_NAME"

IMG_REPO="${IMAGE%:*}"
IMG_TAG="${IMAGE##*:}"
if [[ "${IMG_REPO}" == "${IMAGE}" ]]; then
  IMG_TAG="latest"
fi

echo "==> Deploy local OCI registry"
kubectl create namespace "${REGISTRY_NS}" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${REGISTRY_NS}" apply -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: registry
spec:
  replicas: 1
  selector:
    matchLabels: {app: registry}
  template:
    metadata:
      labels: {app: registry}
    spec:
      containers:
        - name: registry
          image: registry:2
          ports:
            - containerPort: 5000
---
apiVersion: v1
kind: Service
metadata:
  name: registry
spec:
  selector: {app: registry}
  ports:
    - port: 5000
      targetPort: 5000
EOF
kubectl -n "${REGISTRY_NS}" rollout status deploy/registry --timeout=120s

echo "==> Deploy MinIO"
kubectl create namespace "${MINIO_NS}" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${MINIO_NS}" apply -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio
spec:
  replicas: 1
  selector:
    matchLabels: {app: minio}
  template:
    metadata:
      labels: {app: minio}
    spec:
      containers:
        - name: minio
          image: minio/minio:latest
          args: ["server", "/data", "--console-address", ":9001"]
          env:
            - name: MINIO_ROOT_USER
              value: minioadmin
            - name: MINIO_ROOT_PASSWORD
              value: minioadmin
          ports:
            - containerPort: 9000
---
apiVersion: v1
kind: Service
metadata:
  name: minio
spec:
  selector: {app: minio}
  ports:
    - port: 9000
      targetPort: 9000
EOF
kubectl -n "${MINIO_NS}" rollout status deploy/minio --timeout=180s

# Create bucket via ephemeral mc job.
kubectl -n "${MINIO_NS}" delete job minio-init --ignore-not-found
kubectl -n "${MINIO_NS}" apply -f - <<'EOF'
apiVersion: batch/v1
kind: Job
metadata:
  name: minio-init
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: mc
          image: minio/mc:latest
          command:
            - /bin/sh
            - -c
            - |
              mc alias set local http://minio.minio.svc.cluster.local:9000 minioadmin minioadmin
              mc mb -p local/twinops || true
EOF
kubectl -n "${MINIO_NS}" wait --for=condition=complete job/minio-init --timeout=120s

echo "==> Helm install operator"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install "${RELEASE}" deploy/helm/twinops-operator \
  --namespace "${NAMESPACE}" \
  --set createNamespace=false \
  --set image.repository="${IMG_REPO}" \
  --set image.tag="${IMG_TAG}" \
  --set image.pullPolicy=Never \
  --set buildImage="${IMAGE}" \
  --set allowLabFallback=0 \
  --wait --timeout 240s

kubectl -n "${NAMESPACE}" rollout status deploy/twinops-controller-manager --timeout=120s

# S3 credentials Secret
kubectl -n "${NAMESPACE}" create secret generic twinops-s3 \
  --from-literal=access-key-id=minioadmin \
  --from-literal=secret-access-key=minioadmin \
  --dry-run=client -o yaml | kubectl apply -f -

BUNDLE="${ROOT}/usd/generated/operator-oci-s3-e2e-bundle"
rm -rf "${BUNDLE}"
mkdir -p "${BUNDLE}"
sed 's|baseStage: assets/root.usda|baseStage: root.usda|' \
  "${ROOT}/examples/assembly-line/twin.yaml" >"${BUNDLE}/twin.yaml"
cp "${ROOT}/examples/assembly-line/assets/root.usda" "${BUNDLE}/root.usda"
cp "${ROOT}/examples/assembly-line/desired.yaml" "${BUNDLE}/desired.yaml"
cp "${ROOT}/examples/assembly-line/telemetry.json" "${BUNDLE}/telemetry.json"

kubectl -n "$NAMESPACE" delete digitaltwin --all --ignore-not-found
kubectl -n "$NAMESPACE" delete configmap "$CM_NAME" --ignore-not-found
kubectl -n "$NAMESPACE" create configmap "$CM_NAME" \
  --from-file=twin.yaml="${BUNDLE}/twin.yaml" \
  --from-file=root.usda="${BUNDLE}/root.usda" \
  --from-file=desired.yaml="${BUNDLE}/desired.yaml" \
  --from-file=telemetry.json="${BUNDLE}/telemetry.json"

wait_ready() {
  local name="$1"
  for _ in $(seq 1 150); do
    phase="$(kubectl -n "$NAMESPACE" get digitaltwin "$name" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
    uri="$(kubectl -n "$NAMESPACE" get digitaltwin "$name" -o jsonpath='{.status.output.uri}' 2>/dev/null || true)"
    if [[ ( "$phase" == "Ready" || "$phase" == "DriftDetected" ) && -n "$uri" ]]; then
      echo "$phase $uri"
      return 0
    fi
    if [[ "$phase" == "Error" ]]; then
      kubectl -n "$NAMESPACE" get digitaltwin "$name" -o yaml | tail -80 >&2
      kubectl -n "$NAMESPACE" logs deploy/twinops-controller-manager --tail=120 >&2 || true
      return 1
    fi
    sleep 2
  done
  echo "timeout waiting for $name" >&2
  kubectl -n "$NAMESPACE" get digitaltwin "$name" -o yaml | tail -80 >&2 || true
  kubectl -n "$NAMESPACE" logs deploy/twinops-controller-manager --tail=120 >&2 || true
  return 1
}

# --- OCI twin (inline build + oras push) ---
# Local registry has no TLS — enable ORAS plain HTTP.
kubectl -n "${NAMESPACE}" set env deploy/twinops-controller-manager \
  TWINOPS_OCI_PLAIN_HTTP=1
kubectl -n "${NAMESPACE}" rollout status deploy/twinops-controller-manager --timeout=120s

cat <<EOF | kubectl apply -f -
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: ${TWIN_OCI}
  namespace: ${NAMESPACE}
spec:
  artifactSource:
    configMapName: ${CM_NAME}
  intervalSeconds: 10
  build:
    mode: inline
  outputPublish:
    mode: oci
    repository: registry.registry.svc.cluster.local:5000/twinops/artifacts
    keepRevisions: 3
EOF

echo -n "==> Wait OCI publish "
OUT="$(wait_ready "${TWIN_OCI}")"
echo "${OUT}"
URI_OCI="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_OCI" -o jsonpath='{.status.output.uri}')"
if [[ "${URI_OCI}" != oci://*@sha256:* ]]; then
  echo "error: expected immutable oci://repo@sha256:... URI, got ${URI_OCI}" >&2
  exit 1
fi
if [[ "${URI_OCI}" == *labFallback* || "${URI_OCI}" == configmap://* ]]; then
  echo "error: OCI fell back to ConfigMap: ${URI_OCI}" >&2
  exit 1
fi
echo "    oci uri=${URI_OCI}"

# --- S3 twin ---
cat <<EOF | kubectl apply -f -
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: ${TWIN_S3}
  namespace: ${NAMESPACE}
spec:
  artifactSource:
    configMapName: ${CM_NAME}
  intervalSeconds: 10
  build:
    mode: inline
  outputPublish:
    mode: s3
    s3Bucket: twinops
    s3Prefix: e2e
    s3Endpoint: http://minio.minio.svc.cluster.local:9000
    s3Region: us-east-1
    s3PathStyle: true
    s3SecretRef:
      name: twinops-s3
    keepRevisions: 3
EOF

echo -n "==> Wait S3 publish "
OUT="$(wait_ready "${TWIN_S3}")"
echo "${OUT}"
URI_S3="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_S3" -o jsonpath='{.status.output.uri}')"
if [[ "${URI_S3}" != s3://* ]]; then
  echo "error: expected s3:// URI, got ${URI_S3}" >&2
  exit 1
fi
if [[ "${URI_S3}" == *labFallback* || "${URI_S3}" == configmap://* ]]; then
  echo "error: S3 fell back to ConfigMap: ${URI_S3}" >&2
  exit 1
fi
echo "    s3 uri=${URI_S3}"

# --- Job mode + OCI (Job publishes directly, no ConfigMap bundle bridge) ---
TWIN_JOB="assembly-line-job-oci"
cat <<EOF | kubectl apply -f -
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: ${TWIN_JOB}
  namespace: ${NAMESPACE}
spec:
  artifactSource:
    configMapName: ${CM_NAME}
  intervalSeconds: 10
  build:
    mode: job
    activeDeadlineSeconds: 240
  outputPublish:
    mode: oci
    repository: registry.registry.svc.cluster.local:5000/twinops/job-artifacts
    keepRevisions: 3
EOF

echo -n "==> Wait Job+OCI publish "
OUT="$(wait_ready "${TWIN_JOB}")"
echo "${OUT}"
URI_JOB="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB" -o jsonpath='{.status.output.uri}')"
JOB_NAME="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB" -o jsonpath='{.status.build.jobName}')"
if [[ -z "${JOB_NAME}" ]]; then
  JOB_NAME="$(kubectl -n "$NAMESPACE" get jobs -l twinops.io/twin="$TWIN_JOB" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
fi
if [[ -z "${JOB_NAME}" ]]; then
  echo "error: empty jobName for ${TWIN_JOB}" >&2
  kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB" -o yaml | tail -60 >&2
  kubectl -n "$NAMESPACE" get jobs -o wide >&2 || true
  exit 1
fi
if [[ "${URI_JOB}" != oci://*@sha256:* ]]; then
  echo "error: job oci uri invalid: ${URI_JOB}" >&2
  exit 1
fi
# Result ConfigMap must NOT contain the large bundle when mode=oci.
RESULT_CM="$(kubectl -n "$NAMESPACE" get cm -l twinops.io/build-result=true,twinops.io/twin=${TWIN_JOB} -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -n "${RESULT_CM}" ]]; then
  BUNDLE_B64="$(kubectl -n "$NAMESPACE" get cm "${RESULT_CM}" -o jsonpath='{.binaryData.bundle\.tar\.gz}' 2>/dev/null || true)"
  if [[ -n "${BUNDLE_B64}" ]]; then
    echo "error: OCI job result ConfigMap must not carry bundle.tar.gz (size bridge)" >&2
    exit 1
  fi
fi
echo "    job=${JOB_NAME} uri=${URI_JOB}"
# Job path must surface structured drift (not Unknown). Wait briefly for status settle.
DRIFT_JOB=""
for _ in $(seq 1 30); do
  DRIFT_JOB="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB" -o jsonpath='{.status.drift.status}' 2>/dev/null || true)"
  if [[ -n "${DRIFT_JOB}" && "${DRIFT_JOB}" != "Unknown" ]]; then
    break
  fi
  sleep 2
done
if [[ -z "${DRIFT_JOB}" || "${DRIFT_JOB}" == "Unknown" ]]; then
  echo "error: Job+OCI drift status missing/Unknown (got '${DRIFT_JOB}')" >&2
  kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB" -o jsonpath='{.status}' >&2; echo >&2
  # Dump job result CM for diagnosis
  RESULT_CM="$(kubectl -n "$NAMESPACE" get cm -l twinops.io/build-result=true,twinops.io/twin=${TWIN_JOB} -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
  if [[ -n "${RESULT_CM}" ]]; then
    echo "--- result CM ${RESULT_CM} ---" >&2
    kubectl -n "$NAMESPACE" get cm "${RESULT_CM}" -o jsonpath='{.data.result\.json}' >&2; echo >&2
    kubectl -n "$NAMESPACE" get cm "${RESULT_CM}" -o jsonpath='{.metadata.annotations}' >&2; echo >&2
  fi
  kubectl -n "$NAMESPACE" get jobs,pods -l twinops.io/twin=${TWIN_JOB} -o wide >&2 || true
  kubectl -n "$NAMESPACE" logs -l twinops.io/twin=${TWIN_JOB},twinops.io/build=true --tail=80 >&2 || true
  exit 1
fi
echo "    drift.status=${DRIFT_JOB}"

# --- Job mode + S3 (direct Job publish, no ConfigMap bridge) ---
TWIN_JOB_S3="assembly-line-job-s3"
cat <<EOF | kubectl apply -f -
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: ${TWIN_JOB_S3}
  namespace: ${NAMESPACE}
spec:
  artifactSource:
    configMapName: ${CM_NAME}
  intervalSeconds: 10
  build:
    mode: job
    activeDeadlineSeconds: 240
  outputPublish:
    mode: s3
    s3Bucket: twinops
    s3Prefix: e2e-job
    s3Endpoint: http://minio.minio.svc.cluster.local:9000
    s3Region: us-east-1
    s3PathStyle: true
    s3SecretRef:
      name: twinops-s3
    keepRevisions: 3
EOF

echo -n "==> Wait Job+S3 publish "
OUT="$(wait_ready "${TWIN_JOB_S3}")"
echo "${OUT}"
URI_JOB_S3="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB_S3" -o jsonpath='{.status.output.uri}')"
JOB_S3="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB_S3" -o jsonpath='{.status.build.jobName}')"
if [[ -z "${JOB_S3}" ]]; then
  JOB_S3="$(kubectl -n "$NAMESPACE" get jobs -l twinops.io/twin="$TWIN_JOB_S3" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
fi
if [[ "${URI_JOB_S3}" != s3://* ]]; then
  echo "error: job s3 uri invalid: ${URI_JOB_S3}" >&2
  exit 1
fi
if [[ "${URI_JOB_S3}" == *labFallback* || "${URI_JOB_S3}" == configmap://* ]]; then
  echo "error: Job+S3 fell back to ConfigMap: ${URI_JOB_S3}" >&2
  exit 1
fi
RESULT_S3="$(kubectl -n "$NAMESPACE" get cm -l twinops.io/build-result=true,twinops.io/twin=${TWIN_JOB_S3} -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -n "${RESULT_S3}" ]]; then
  BUNDLE_B64="$(kubectl -n "$NAMESPACE" get cm "${RESULT_S3}" -o jsonpath='{.binaryData.bundle\.tar\.gz}' 2>/dev/null || true)"
  if [[ -n "${BUNDLE_B64}" ]]; then
    echo "error: S3 job result ConfigMap must not carry bundle.tar.gz" >&2
    exit 1
  fi
fi
DRIFT_S3="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB_S3" -o jsonpath='{.status.drift.status}')"
if [[ -z "${DRIFT_S3}" || "${DRIFT_S3}" == "Unknown" ]]; then
  echo "error: Job+S3 drift status missing/Unknown (got '${DRIFT_S3}')" >&2
  exit 1
fi
echo "    job=${JOB_S3} uri=${URI_JOB_S3} drift=${DRIFT_S3}"

# --- Publish-spec change creates a NEW Job (same input, different mode) ---
# Switch Job-OCI twin to a different repository → new execution key → new Job name.
PREV_JOB="${JOB_NAME}"
cat <<EOF | kubectl apply -f -
apiVersion: twinops.io/v1alpha1
kind: DigitalTwin
metadata:
  name: ${TWIN_JOB}
  namespace: ${NAMESPACE}
spec:
  artifactSource:
    configMapName: ${CM_NAME}
  intervalSeconds: 10
  build:
    mode: job
    activeDeadlineSeconds: 240
  outputPublish:
    mode: oci
    repository: registry.registry.svc.cluster.local:5000/twinops/job-artifacts-v2
    keepRevisions: 3
EOF

echo -n "==> Wait Job re-key after publish-spec change "
NEW_JOB=""
NEW_URI=""
for _ in $(seq 1 120); do
  NEW_JOB="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB" -o jsonpath='{.status.build.jobName}' 2>/dev/null || true)"
  NEW_URI="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB" -o jsonpath='{.status.output.uri}' 2>/dev/null || true)"
  phase="$(kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  if [[ -n "${NEW_JOB}" && "${NEW_JOB}" != "${PREV_JOB}" && "${NEW_URI}" == oci://*job-artifacts-v2* && ( "$phase" == "Ready" || "$phase" == "DriftDetected" ) ]]; then
    echo "ok"
    break
  fi
  sleep 2
done
if [[ -z "${NEW_JOB}" || "${NEW_JOB}" == "${PREV_JOB}" ]]; then
  echo "error: expected NEW Job after repository change (old=${PREV_JOB} new=${NEW_JOB})" >&2
  kubectl -n "$NAMESPACE" get digitaltwin "$TWIN_JOB" -o yaml | tail -60 >&2
  exit 1
fi
echo "    job ${PREV_JOB} → ${NEW_JOB}"
echo "    uri=${NEW_URI}"

echo "operator-oci-s3-e2e OK"
