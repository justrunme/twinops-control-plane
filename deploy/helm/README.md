# TwinOps Helm charts

## Charts

| Chart | Path | Purpose |
| --- | --- | --- |
| `twinops` | [twinops/](twinops/) | Umbrella (operator + live values stub) |
| `twinops-operator` | [twinops-operator/](twinops-operator/) | DigitalTwin CRD + controller |

## Umbrella layout

```bash
helm dependency update ./deploy/helm/twinops
helm upgrade --install twinops ./deploy/helm/twinops \
  --namespace twinops-system --create-namespace
```

Still compose for demos:

1. **operator** — via umbrella / subchart
2. **live** — `make docker-live-up` (Deployment stub documented in umbrella values)
3. **mqtt** — anonymous compose or ACL profile (`docker-compose.mqtt-acl.yml`)
4. **observability** — `deploy/observability/` Grafana + ServiceMonitor stubs

## Values guidance

- Keep live API behind a token (`TWINOPS_API_TOKEN`) before any non-localhost Service
- Do not expose anonymous MQTT outside a trusted lab network
- Point `spec.liveAPIURL` on DigitalTwin CRs at the live Service for status sync
