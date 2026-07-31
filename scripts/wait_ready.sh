#!/usr/bin/env bash
# Wait until TwinOps live API reports /api/ready.
# Usage: ./scripts/wait_ready.sh [base_url] [timeout_seconds]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="${1:-http://127.0.0.1:8080}"
TIMEOUT="${2:-30}"
TWINOPSCTL="${ROOT}/.venv/bin/twinopsctl"

if [[ ! -x "$TWINOPSCTL" ]]; then
  echo "error: missing $TWINOPSCTL (run make install)" >&2
  exit 2
fi

deadline=$((SECONDS + TIMEOUT))
echo -n "==> Waiting for ready at ${BASE}"
while (( SECONDS < deadline )); do
  if "$TWINOPSCTL" ready --base-url "$BASE" >/dev/null 2>&1; then
    echo " OK"
    "$TWINOPSCTL" ready --base-url "$BASE"
    exit 0
  fi
  echo -n "."
  sleep 0.25
done

echo
echo "Timed out waiting for ${BASE}/api/ready after ${TIMEOUT}s" >&2
exit 1
