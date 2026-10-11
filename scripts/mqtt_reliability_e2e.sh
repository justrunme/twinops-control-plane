#!/usr/bin/env bash
# MQTT reliability E2E: Mosquitto replay of out-of-order / duplicate / stale streams.
# Usage: ./scripts/mqtt_reliability_e2e.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${ROOT}/deploy/demo/docker-compose.mqtt.yml"
COMPOSE_PROJECT="${TWINOPS_MQTT_RELIABILITY_PROJECT:-twinops-mqtt-reliability}"
MQTT_HOST="${TWINOPS_MQTT_HOST:-127.0.0.1}"
MQTT_PORT="${TWINOPS_MQTT_PORT:-12883}"
OUT_DIR="${TWINOPS_MQTT_RELIABILITY_OUT:-/tmp/twinops-mqtt-reliability}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need docker

if [[ ! -x "${ROOT}/.venv/bin/python" ]]; then
  make install
fi
PYTHON="${ROOT}/.venv/bin/python"
mkdir -p "$OUT_DIR"

cleanup() {
  docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Starting Mosquitto (${COMPOSE_PROJECT}) on ${MQTT_HOST}:${MQTT_PORT}"
MQTT_HOST_PORT="$MQTT_PORT" docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" up -d

echo -n "==> Waiting for broker"
for _ in $(seq 1 40); do
  if "$PYTHON" - <<PY >/dev/null 2>&1
import socket
socket.create_connection(("${MQTT_HOST}", int("${MQTT_PORT}")), timeout=1).close()
PY
  then
    echo " OK"
    break
  fi
  echo -n "."
  sleep 0.25
done

"$PYTHON" - <<'PY' "$MQTT_HOST" "$MQTT_PORT" "$OUT_DIR"
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import paho.mqtt.client as mqtt

from twinops.telemetry.ingest import ObservationIngest, TopicBinding
from twinops.telemetry.reliability import SensorTracker

host, port, out_dir = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
tracker = SensorTracker(ttl_seconds=0.4, dedupe_window_seconds=30, max_skew_seconds=3600)
ingest = ObservationIngest(
    [
        TopicBinding(
            topic="factory/robot-01/temperature",
            prim="/World/Factory/LineA/Robot01",
            attribute="twinops:temperature",
        ),
        TopicBinding(
            topic="factory/robot-01/status",
            prim="/World/Factory/LineA/Robot01",
            attribute="twinops:status",
        ),
        TopicBinding(
            topic="factory/robot-01/offline",
            prim="/World/Factory/LineA/Robot01",
            attribute="twinops:offlineMarker",
        ),
    ],
    tracker=tracker,
)

received = {"n": 0}
connected_once = {"v": False}

def on_message(_c, _u, msg):
    ingest.handle_message(msg.topic, msg.payload)
    received["n"] += 1

def on_connect(client, _u, _flags, reason_code, _props=None):
    rc = int(getattr(reason_code, "value", reason_code) or 0)
    if rc != 0:
        return
    client.subscribe("factory/#", qos=1)
    if connected_once["v"]:
        tracker.note_session_resume()
    else:
        connected_once["v"] = True

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id="twinops-reliability-e2e",
    clean_session=False,
)
client.on_message = on_message
client.on_connect = on_connect
client.connect(host, port, keepalive=30)
client.loop_start()

deadline = time.time() + 5
while time.time() < deadline and not connected_once["v"]:
    time.sleep(0.05)
assert connected_once["v"], "ingest client failed to connect"

pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="twinops-reliability-pub")
pub.connect(host, port, keepalive=30)
pub.loop_start()

def publish(topic, payload):
    pub.publish(topic, json.dumps(payload), qos=1)
    time.sleep(0.05)

base = datetime.now(UTC)
publish("factory/robot-01/temperature", {
    "value": 50.0, "sequence": 2, "source": "plc",
    "timestamp": (base + timedelta(seconds=2)).isoformat().replace("+00:00", "Z"),
    "messageId": "t-2",
})
publish("factory/robot-01/temperature", {
    "value": 40.0, "sequence": 1, "source": "plc",
    "timestamp": (base + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
    "messageId": "t-1",
})
dup = {
    "value": 50.0, "sequence": 2, "source": "plc",
    "timestamp": (base + timedelta(seconds=2)).isoformat().replace("+00:00", "Z"),
    "messageId": "t-2",
}
publish("factory/robot-01/temperature", dup)
publish("factory/robot-01/status", {
    "value": "running", "sequence": 1, "source": "plc",
    "timestamp": base.isoformat().replace("+00:00", "Z"),
    "messageId": "s-1",
})

deadline = time.time() + 5
while time.time() < deadline and received["n"] < 4:
    time.sleep(0.05)

time.sleep(0.55)
stale = ingest.apply_stale()
assert "factory/robot-01/status" in stale, stale
snap = ingest.status()
assert snap["outOfOrderDropped"] >= 1, snap
assert snap["duplicatesDropped"] >= 1, snap
assert snap["staleSensors"] >= 1, snap
attrs = ingest.merge_observations({"observations": [], "timestamp": "t", "source": "x"})
status_attrs = next(
    o["attributes"] for o in attrs["observations"] if o["prim"].endswith("Robot01")
)
assert status_attrs.get("twinops:status") == "STALE", status_attrs
assert status_attrs.get("twinops:temperature") == 50.0, status_attrs

resumes_before = tracker.metrics.session_resumes
offline_before = received["n"]
client.loop_stop()
client.disconnect()
time.sleep(0.4)

publish("factory/robot-01/offline", {
    "value": "queued-while-down", "sequence": 1, "source": "plc",
    "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    "messageId": "off-1",
})
time.sleep(0.2)

client2 = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id="twinops-reliability-e2e",
    clean_session=False,
)
client2.on_message = on_message
client2.on_connect = on_connect
client2.connect(host, port, keepalive=30)
client2.loop_start()

deadline = time.time() + 8
delivered = False
while time.time() < deadline:
    if received["n"] > offline_before:
        delivered = True
        break
    time.sleep(0.05)
assert delivered, f"QoS1 message not delivered after reconnect (n={received['n']})"
assert tracker.metrics.session_resumes == resumes_before + 1, tracker.metrics.session_resumes
snap2 = tracker.snapshot()
assert "factory/robot-01/offline" in snap2, list(snap2)
assert snap2["factory/robot-01/offline"].value == "queued-while-down"

report = {
    "outOfOrderDropped": snap["outOfOrderDropped"],
    "duplicatesDropped": snap["duplicatesDropped"],
    "staleSensors": snap["staleSensors"],
    "sessionResumes": tracker.metrics.session_resumes,
    "offlineDelivered": True,
    "lastTemperature": status_attrs.get("twinops:temperature"),
    "status": status_attrs.get("twinops:status"),
    "conditions": snap["conditions"],
}
out_dir.joinpath("mqtt-reliability-report.json").write_text(
    json.dumps(report, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(report, indent=2))
print("mqtt_reliability_e2e OK")
client2.loop_stop()
client2.disconnect()
pub.loop_stop()
pub.disconnect()
PY
