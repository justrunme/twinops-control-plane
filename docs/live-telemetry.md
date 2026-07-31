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

The simulator always publishes on an in-process bus. To also publish to a broker:

```bash
docker compose -f deploy/demo/docker-compose.mqtt.yml up -d
twinopsctl serve --mqtt-host 127.0.0.1 --mqtt-port 1883
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
    "port": 1883
  }
}
```

### Smoke test

One-command check that Mosquitto receives `factory/#` telemetry:

```bash
make mqtt-smoke
```

This starts Mosquitto via Compose, runs `twinopsctl serve --mqtt-host`,
subscribes with paho-mqtt, and tears everything down.
