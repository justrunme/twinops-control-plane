#!/usr/bin/env bash
# Local supply-chain smoke: pip-audit + govulncheck + optional npm audit.
# Full Trivy/Syft runs in .github/workflows/security.yml.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-${ROOT}/.venv/bin/python}"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON=python3
fi

if ! "${PYTHON}" -m pip_audit -h >/dev/null 2>&1; then
  echo "==> Installing pip-audit"
  "${PYTHON}" -m pip install -q pip-audit
fi

echo "==> pip-audit"
"${PYTHON}" -m pip_audit

echo "==> govulncheck"
if ! command -v govulncheck >/dev/null 2>&1; then
  go install golang.org/x/vuln/cmd/govulncheck@latest
fi
govulncheck ./...

if [[ -f web/package-lock.json ]] && command -v npm >/dev/null 2>&1; then
  echo "==> npm audit (web)"
  (cd web && npm audit --audit-level=high || true)
fi

echo "==> ruff"
if [[ -x "${ROOT}/.venv/bin/ruff" ]]; then
  "${ROOT}/.venv/bin/ruff" check python tests
else
  ruff check python tests
fi

echo "security_scan OK"
