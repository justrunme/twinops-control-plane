# Live telemetry

Milestone 4 starter: an in-process MQTT-style simulator feeds observed twin state into continuous drift evaluation.

## Run

```bash
make install
make serve
```

API:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | liveness |
| `GET /api/twin` | twin + latest drift + timeline snapshot |
| `GET /api/drift/latest` | latest drift report |
| `GET /api/scene` | OpenUSD prim highlight snapshot (`twinops.highlight.v1`) |
| `GET /api/timeline` | recent telemetry/drift events |
| `POST /api/simulate/spike` | force overheating robot event |
| `POST /api/reconcile` | generate proposal, apply USD overlay, heal line |
| `GET /api/proposal/latest` | last reconciliation proposal |
| `WS /ws/events` | live event stream |

Demo flow in the web UI:

1. **Trigger heat spike** → CRITICAL / DRIFT findings appear  
2. **Apply reconciliation** → USD overlay applied, simulator healed, twin returns to SYNCED  


## MQTT bridge (optional)

The simulator always publishes on an in-process bus. With a broker you get a
**bidirectional** bridge:

- **publish** — simulator telemetry → `factory/#` (payload includes `"source": "twinops"`)
- **ingest** — external PLC/MQTT → observed twin attributes (echoes from TwinOps ignored)

```bash
docker compose -f deploy/demo/docker-compose.mqtt.yml up -d
twinopsctl serve --mqtt-host 127.0.0.1 --mqtt-port 1883
# publish-only:
# twinopsctl serve --mqtt-host 127.0.0.1 --no-mqtt-ingest
```

Requires `pip install -e ".[live]"` (included in `make install` via `.[dev]`).

`GET /api/health` reports MQTT bridge status:

```json
{
  "status": "ok",
  "mqtt": {
    "requested": true,
    "enabled": true,
    "host": "127.0.0.1",
    "port": 1883,
    "ingest": {
      "requested": true,
      "enabled": true,
      "received": 1,
      "lastTopic": "factory/robot-01/temperature"
    }
  }
}
```

External inject example:

```bash
mosquitto_pub -h 127.0.0.1 -t factory/robot-01/temperature \
  -m '{"value": 91.5, "source": "factory-plc"}'
```

### Smoke test

One-command check for publish **and** ingest:

```bash
make mqtt-smoke
```

Starts Mosquitto, runs `twinopsctl serve --mqtt-host`, verifies outbound
`factory/#` messages, publishes an external heat spike, and asserts critical drift.
