# TwinOps Helm charts

## Charts

| Chart | Path | Purpose |
| --- | --- | --- |
| `twinops-operator` | [twinops-operator/](twinops-operator/) | DigitalTwin CRD + controller |

## Umbrella layout (planned)

A future `twinops` umbrella chart will compose:

1. **operator** — reconcile `DigitalTwin` CRs
2. **live** — `twinopsctl serve` Deployment + Service (optional)
3. **mqtt** — Mosquitto for demo telemetry (optional, anonymous only for local)
4. **observability** — ServiceMonitor / Grafana dashboard ConfigMap from `deploy/observability/`

Until the umbrella lands, install pieces separately:

```bash
helm upgrade --install twinops-operator ./deploy/helm/twinops-operator
# live + mqtt: use docker compose for demos
make docker-live-up
```

## Values guidance

- Keep live API behind a token (`TWINOPS_API_TOKEN`) before any non-localhost Service
- Do not expose anonymous MQTT outside a trusted lab network
- Point `spec.liveAPIURL` on DigitalTwin CRs at the live Service for status sync
