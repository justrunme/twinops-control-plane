#!/usr/bin/env bash
# Local clean-room consistency checks for TwinOps 1.0 (no extra CI job).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TWINOPSCTL="${TWINOPSCTL:-${ROOT}/.venv/bin/twinopsctl}"
PYTHON="${PYTHON:-${ROOT}/.venv/bin/python}"

if [[ ! -x "${TWINOPSCTL}" ]]; then
  echo "==> make install"
  make install
fi

echo "==> Version consistency"
CLI_VER="$("${TWINOPSCTL}" version | awk '{print $NF}')"
PY_VER="$("${PYTHON}" -c 'from twinops import __version__; print(__version__)')"
PYPROJECT_VER="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)"
HELM_APP="$(sed -n 's/^appVersion: "\(.*\)"/\1/p' deploy/helm/twinops/Chart.yaml | head -1)"
OPERATOR_APP="$(sed -n 's/^appVersion: "\(.*\)"/\1/p' deploy/helm/twinops-operator/Chart.yaml | head -1)"

echo "    cli=${CLI_VER} package=${PY_VER} pyproject=${PYPROJECT_VER}"
echo "    helm.appVersion=${HELM_APP} operator.appVersion=${OPERATOR_APP}"

for v in "${CLI_VER}" "${PY_VER}" "${PYPROJECT_VER}" "${HELM_APP}" "${OPERATOR_APP}"; do
  if [[ "${v}" != "1.0.0" ]]; then
    echo "error: expected version 1.0.0, got ${v}" >&2
    exit 1
  fi
done

echo "==> No secrets in tracked example configs"
if git grep -nE 'BEGIN (RSA |OPENSSH )?PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}' -- \
  ':!*.sqlite' ':!**/node_modules/**' 2>/dev/null; then
  echo "error: possible secret material in tracked files" >&2
  exit 1
fi
echo "    OK"

echo "==> Git worktree clean of generated demo debris under examples/"
if git status --porcelain examples/ | grep -E 'generated/|\.sqlite$' >/dev/null 2>&1; then
  echo "error: unexpected generated artifacts under examples/" >&2
  git status --porcelain examples/
  exit 1
fi
echo "    OK"

echo "==> README entrypoints exist"
for cmd in "make live-demo" "make e2e-demo" "make streaming-sidecar-smoke" "make verify-all"; do
  target="${cmd#make }"
  if ! grep -q "^${target}:" Makefile; then
    echo "error: Makefile missing target ${target}" >&2
    exit 1
  fi
done
echo "    OK"

echo "cleanroom_check OK"
