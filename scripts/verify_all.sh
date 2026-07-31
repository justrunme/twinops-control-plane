#!/usr/bin/env bash
# Local gate before pushing TwinOps changes.
# Usage: ./scripts/verify_all.sh [--with-mqtt]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WITH_MQTT=0
for arg in "$@"; do
  case "$arg" in
    --with-mqtt) WITH_MQTT=1 ;;
    -h|--help)
      sed -n '2,4p' "$0"
      exit 0
      ;;
  esac
done

echo "==> make test"
make test

echo "==> make lint"
make lint

echo "==> mqtt topic catalog sync check"
"${ROOT}/.venv/bin/python" scripts/sync_mqtt_topics.py --check

echo "==> make go-test"
make go-test

echo "==> make plm-demo"
make plm-demo

echo "==> make live-demo-smoke"
make live-demo-smoke

if [[ "$WITH_MQTT" -eq 1 ]]; then
  echo "==> make mqtt-smoke"
  make mqtt-smoke
else
  echo "==> skip mqtt-smoke (pass --with-mqtt to enable)"
fi

echo
echo "verify_all OK"
