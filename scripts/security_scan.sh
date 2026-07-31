#!/usr/bin/env bash
# Local / on-demand dependency security scan.
# CI: .github/workflows/security.yml (workflow_dispatch + release only).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-${ROOT}/.venv/bin/python}"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON=python3
fi

if ! "${PYTHON}" -m pip_audit -h >/dev/null 2>&1; then
  echo "==> Installing pip-audit (dev tool)"
  "${PYTHON}" -m pip install -q pip-audit
fi

echo "==> pip-audit"
"${PYTHON}" -m pip_audit

echo "==> ruff"
if [[ -x "${ROOT}/.venv/bin/ruff" ]]; then
  "${ROOT}/.venv/bin/ruff" check python tests
else
  ruff check python tests
fi

echo "security_scan OK"
