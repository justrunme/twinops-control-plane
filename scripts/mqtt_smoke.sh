#!/usr/bin/env bash
# TwinOps Mosquitto MQTT bridge smoke test.
#
# Starts eclipse-mosquitto, runs twinopsctl serve --mqtt-host, subscribes to
# factory/#, and asserts at least one published telemetry message arrives.
#
# Usage:
#   ./scripts/mqtt_smoke.sh
#   make mqtt-smoke
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${ROOT}/deploy/demo/docker-compose.mqtt.yml"
HOST="${TWINOPS_HOST:-127.0.0.1}"
PORT="${TWINOPS_MQTT_SMOKE_PORT:-18088}"
MQTT_HOST="${TWINOPS_MQTT_HOST:-127.0.0.1}"
# Dedicated host port avoids clashing with a local broker already on 1883.
MQTT_PORT="${TWINOPS_MQTT_PORT:-11883}"
BASE="http://${HOST}:${PORT}"
KEEP_LOG="${TWINOPS_MQTT_SMOKE_LOG:-/tmp/twinops-mqtt-smoke.log}"
COMPOSE_PROJECT="${TWINOPS_MQTT_COMPOSE_PROJECT:-twinops-mqtt-smoke}"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 1
  }
}

need docker
need curl
docker info >/dev/null 2>&1 || {
  echo "Docker is not running. Start Docker Desktop and retry." >&2
  exit 1
}

if [[ ! -x "$ROOT/.venv/bin/twinopsctl" ]]; then
  echo "==> Installing TwinOps (make install)"
  make install
fi

TWINOPSCTL="$ROOT/.venv/bin/twinopsctl"
PYTHON="$ROOT/.venv/bin/python"
SERVER_PID=""

cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Starting Mosquitto (${COMPOSE_PROJECT}) on ${MQTT_HOST}:${MQTT_PORT}"
MQTT_HOST_PORT="$MQTT_PORT" docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" up -d

echo -n "==> Waiting for MQTT ${MQTT_HOST}:${MQTT_PORT}"
for _ in $(seq 1 40); do
  if "$PYTHON" - <<PY >/dev/null 2>&1
import socket
s = socket.create_connection(("${MQTT_HOST}", int("${MQTT_PORT}")), timeout=1)
s.close()
PY
  then
    echo " OK"
    break
  fi
  echo -n "."
  sleep 0.25
done

"$PYTHON" - <<PY
import socket
socket.create_connection(("${MQTT_HOST}", int("${MQTT_PORT}")), timeout=2).close()
print("mqtt port open")
PY

echo "==> Starting TwinOps serve with MQTT bridge on ${BASE}"
: >"$KEEP_LOG"
"$TWINOPSCTL" serve \
  --example examples/assembly-line \
  --host "$HOST" \
  --port "$PORT" \
  --interval 0.5 \
  --mqtt-host "$MQTT_HOST" \
  --mqtt-port "$MQTT_PORT" \
  >"$KEEP_LOG" 2>&1 &
SERVER_PID=$!

echo -n "==> Waiting for health"
for _ in $(seq 1 40); do
  if curl -fsS "$BASE/api/health" >/dev/null 2>&1; then
    echo " OK"
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo
    echo "Server exited early. Log: $KEEP_LOG"
    tail -n 60 "$KEEP_LOG" || true
    exit 1
  fi
  echo -n "."
  sleep 0.25
done

HEALTH="$(curl -fsS "$BASE/api/health")"
echo "$HEALTH" | "$PYTHON" -c '
import json, sys
body = json.load(sys.stdin)
mqtt = body.get("mqtt") or {}
ingest = mqtt.get("ingest") or {}
assert body.get("status") == "ok", body
assert mqtt.get("requested") is True, mqtt
assert mqtt.get("enabled") is True, mqtt
assert ingest.get("enabled") is True, ingest
print("health mqtt.enabled =", mqtt.get("enabled"), "ingest.enabled =", ingest.get("enabled"))
'

echo "==> Subscribing to factory/# (expect telemetry within 15s)"
"$PYTHON" - "$MQTT_HOST" "$MQTT_PORT" <<'PY'
import json
import sys
import time

import paho.mqtt.client as mqtt

host = sys.argv[1]
port = int(sys.argv[2])
seen: list[tuple[str, dict]] = []
done = False


def on_message(_client, _userdata, msg):
    global done
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        payload = {"raw": msg.payload.decode("utf-8", errors="replace")}
    seen.append((msg.topic, payload))
    if msg.topic.startswith("factory/"):
        done = True


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="twinops-mqtt-smoke")
client.on_message = on_message
client.connect(host, port, keepalive=30)
client.subscribe("factory/#")
client.loop_start()

deadline = time.time() + 15
while time.time() < deadline and not done:
    time.sleep(0.1)

client.loop_stop()
client.disconnect()

if not seen:
    print("no MQTT messages received on factory/#", file=sys.stderr)
    sys.exit(1)

topic, payload = seen[0]
print(f"received {topic}: {json.dumps(payload, sort_keys=True)}")
assert "attribute" in payload or "raw" in payload
print(f"mqtt publish smoke OK ({len(seen)} message(s))")
PY

echo "==> Publishing external heat spike via MQTT ingest"
"$PYTHON" - "$MQTT_HOST" "$MQTT_PORT" <<'PY'
import json
import sys

import paho.mqtt.client as mqtt

host = sys.argv[1]
port = int(sys.argv[2])
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="twinops-mqtt-injector")
client.connect(host, port, keepalive=30)
payload = {
    "prim": "/World/Factory/LineA/Robot01",
    "attribute": "twinops:temperature",
    "value": 91.5,
    "source": "factory-plc",
}
client.publish(
    "factory/robot-01/temperature",
    json.dumps(payload),
    qos=1,
)
client.loop(timeout=1.0)
client.disconnect()
print("published external temperature=91.5")
PY

echo -n "==> Waiting for ingest + critical drift"
for _ in $(seq 1 40); do
  BODY="$(curl -fsS "$BASE/api/health")"
  OK="$("$PYTHON" -c '
import json, sys
body = json.loads(sys.argv[1])
ingest = (body.get("mqtt") or {}).get("ingest") or {}
print("1" if int(ingest.get("received") or 0) >= 1 else "0")
' "$BODY")"
  if [[ "$OK" == "1" ]]; then
    echo " OK"
    break
  fi
  echo -n "."
  sleep 0.25
done

curl -fsS "$BASE/api/health" | "$PYTHON" -c '
import json, sys
body = json.load(sys.stdin)
ingest = (body.get("mqtt") or {}).get("ingest") or {}
assert int(ingest.get("received") or 0) >= 1, ingest
assert ingest.get("lastTopic") == "factory/robot-01/temperature", ingest
print("ingest received =", ingest.get("received"), "lastValue =", ingest.get("lastValue"))
'

curl -fsS "$BASE/api/twin" | "$PYTHON" -c '
import json, sys
body = json.load(sys.stdin)
temp = body.get("simulator", {}).get("robot_temp")
assert float(temp) >= 90, body.get("simulator")
findings = ((body.get("drift") or {}).get("status") or {}).get("findings") or []
critical = [
    f for f in findings
    if f.get("attribute") == "twinops:temperature" and f.get("status") == "CRITICAL"
]
assert critical, findings[:8]
print("ingest drift OK: robot_temp=", temp, "critical_findings=", len(critical))
'

echo
echo "Mosquitto MQTT publish+ingest smoke succeeded."
echo "Log: $KEEP_LOG"
