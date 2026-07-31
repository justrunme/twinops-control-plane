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
| `GET /api/timeline` | recent telemetry/drift events |
| `POST /api/simulate/spike` | force overheating robot event |
| `WS /ws/events` | live event stream |

## MQTT bridge (optional)

The simulator always publishes on an in-process bus. To also publish to a broker:

```bash
docker compose -f deploy/demo/docker-compose.mqtt.yml up -d
twinopsctl serve --mqtt-host 127.0.0.1 --mqtt-port 1883
```

Requires `pip install -e ".[live]"` (included in `make install` via `.[dev]`).
