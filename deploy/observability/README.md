# TwinOps observability stubs

## Prometheus

Scrape the live API Prometheus exposition. Ready-to-merge snippet:
[`prometheus-scrape.snippet.yml`](prometheus-scrape.snippet.yml).

```yaml
# scrape snippet (add to your Prometheus config)
scrape_configs:
  - job_name: twinops-live
    metrics_path: /metrics
    static_configs:
      - targets: ["127.0.0.1:8080"]
```

Key series (see `LiveDriftRuntime.metrics_prometheus`):

- `twinops_drift_has_drift`
- `twinops_drift_findings{status=…}`
- `twinops_scene_highlighted_prims`
- `twinops_mqtt_ingest_received_total`
- `twinops_robot_temperature_celsius`

## Grafana

Import [`grafana/twinops-overview.json`](grafana/twinops-overview.json) into a Grafana that scrapes the job above.

## Auth note

If `TWINOPS_API_TOKEN` is set, `/metrics` stays public for scrape probes; protect the network path instead.
