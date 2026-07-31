#!/usr/bin/env bash
# Lab smoke: start TLS Mosquitto, publish/subscribe once with paho over TLS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CA="${CA:-${ROOT}/deploy/demo/certs/server.crt}"
HOST="${MQTT_HOST:-127.0.0.1}"
PORT="${MQTT_PORT:-8883}"
TOPIC="${TOPIC:-twinops/lab/tls-smoke}"

make mqtt-tls-up

PYTHON="${PYTHON:-${ROOT}/.venv/bin/python}"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON=python3
fi

"${PYTHON}" - <<PY
import ssl
import time
import paho.mqtt.client as mqtt

host = "${HOST}"
port = int("${PORT}")
topic = "${TOPIC}"
ca = "${CA}"

got = {"ok": False}

def on_message(_c, _u, msg):
    got["ok"] = msg.payload == b"twinops-tls-ok"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="twinops-tls-smoke")
client.tls_set(ca_certs=ca)
client.on_message = on_message
client.connect(host, port, keepalive=30)
client.subscribe(topic)
client.loop_start()
time.sleep(0.3)
client.publish(topic, b"twinops-tls-ok", qos=0)
for _ in range(20):
    if got["ok"]:
        break
    time.sleep(0.1)
client.loop_stop()
client.disconnect()
if not got["ok"]:
    raise SystemExit("mqtt tls smoke failed: no matching message")
print(f"mqtt tls smoke ok: {host}:{port} topic={topic}")
PY

echo "==> Stopping TLS broker"
make mqtt-tls-down
