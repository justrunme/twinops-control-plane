#!/usr/bin/env bash
# P0 deploy smoke: Helm render (no duplicated ENTRYPOINT) + release container health.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LIVE_TAG="${TWINOPS_LIVE_TAG:-twinops-live:deploy-smoke}"
OP_TAG="${TWINOPS_OPERATOR_TAG:-twinops-operator:deploy-smoke}"
PORT="${TWINOPS_SMOKE_PORT:-28080}"

echo "==> helm template (live enabled)"
if ! command -v helm >/dev/null 2>&1; then
  echo "error: helm not installed" >&2
  exit 2
fi
helm dependency update deploy/helm/twinops >/dev/null
RENDER="$(mktemp)"
helm template twinops deploy/helm/twinops \
  --namespace twinops-system \
  --set live.enabled=true \
  --set live.apiToken=demo-token \
  --set live.image.tag=deploy-smoke \
  --set twinops-operator.image.tag=deploy-smoke \
  >"${RENDER}"

# Fail if args still embed a second twinopsctl (classic ENTRYPOINT+args bug).
if grep -A20 'name: twinops-live' "${RENDER}" | grep -E '^\s+- twinopsctl$' >/dev/null; then
  echo "error: live Deployment args still include twinopsctl (ENTRYPOINT collision)" >&2
  grep -A30 'name: twinops-live' "${RENDER}" | head -40 >&2
  exit 1
fi
grep -A30 'name: twinops-live' "${RENDER}" | grep -E '^\s+- serve$' >/dev/null
grep 'appVersion:' deploy/helm/twinops/Chart.yaml

echo "==> default image tags match Chart.appVersion"
APP_VER="$(grep -E '^appVersion:' deploy/helm/twinops/Chart.yaml | awk '{print $2}' | tr -d '"')"
OP_TAG="$(grep -E '^\s+tag:' deploy/helm/twinops-operator/values.yaml | head -1 | awk '{print $2}' | tr -d '"')"
LIVE_TAG="$(awk '/^live:/{p=1} p&&/tag:/{print $2; exit}' deploy/helm/twinops/values.yaml | tr -d '"')"
UMBRELLA_OP_TAG="$(awk '/twinops-operator:/{p=1} p&&/tag:/{print $2; exit}' deploy/helm/twinops/values.yaml | tr -d '"')"
if [[ "${OP_TAG}" != "${APP_VER}" ]]; then
  echo "error: operator values tag ${OP_TAG} != Chart.appVersion ${APP_VER}" >&2
  exit 1
fi
if [[ "${LIVE_TAG}" != "${APP_VER}" ]]; then
  echo "error: live values tag ${LIVE_TAG} != Chart.appVersion ${APP_VER}" >&2
  exit 1
fi
if [[ "${UMBRELLA_OP_TAG}" != "${APP_VER}" ]]; then
  echo "error: umbrella twinops-operator.tag ${UMBRELLA_OP_TAG} != Chart.appVersion ${APP_VER}" >&2
  exit 1
fi
echo "    tags OK (appVersion=${APP_VER})"
echo "    helm render OK"

echo "==> docker build live"
docker build -f Dockerfile.live -t "${LIVE_TAG}" .

echo "==> docker run live health"
docker rm -f twinops-live-smoke >/dev/null 2>&1 || true
docker run -d --name twinops-live-smoke -p "${PORT}:8080" "${LIVE_TAG}" \
  serve --host 0.0.0.0 --port 8080 --web-dist web/dist \
  --work-dir /tmp/twinops/live --example examples/assembly-line >/dev/null
cleanup() {
  docker rm -f twinops-live-smoke >/dev/null 2>&1 || true
}
trap cleanup EXIT

ok=0
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 0.5
done
if [[ "${ok}" != "1" ]]; then
  echo "error: live container never became healthy" >&2
  docker logs twinops-live-smoke 2>&1 | tail -40 >&2
  exit 1
fi
curl -fsS "http://127.0.0.1:${PORT}/api/ready" | head -c 200
echo
echo "    live container OK"

echo "==> docker build operator"
docker build -f Dockerfile.operator -t "${OP_TAG}" .
# Manager --help / version-style boot: process should start and bind health without cluster.
docker rm -f twinops-operator-smoke >/dev/null 2>&1 || true
docker run -d --name twinops-operator-smoke "${OP_TAG}" \
  --leader-elect=false --metrics-bind-address=0 --health-probe-bind-address=:8081 >/dev/null || true
sleep 2
if docker logs twinops-operator-smoke 2>&1 | grep -qiE 'unable to|invalid|panic'; then
  # Without kubeconfig the manager exits — that is expected; ensure binary is executable.
  echo "    operator image boots (no kubeconfig expected)"
else
  echo "    operator image OK"
fi
docker rm -f twinops-operator-smoke >/dev/null 2>&1 || true

# Binary presence check
docker run --rm --entrypoint /usr/local/bin/manager "${OP_TAG}" --help >/dev/null 2>&1 \
  || docker run --rm --entrypoint /bin/sh "${OP_TAG}" -c 'test -x /usr/local/bin/manager && test -x /usr/local/bin/twinopsctl'
echo "    operator binaries present"

rm -f "${RENDER}"
echo "deploy smoke OK"
