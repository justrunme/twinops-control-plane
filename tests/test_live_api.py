from pathlib import Path

from fastapi.testclient import TestClient
from twinops.api.app import create_app
from twinops.telemetry.bus import TelemetryBus
from twinops.telemetry.simulator import AssemblyLineSimulator

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def test_simulator_tick_publishes_events() -> None:
    bus = TelemetryBus()
    seen: list[str] = []
    bus.subscribe(lambda event: seen.append(event.topic))
    sim = AssemblyLineSimulator(bus, seed=1)
    events = sim.tick()
    assert len(events) >= 5
    assert "factory/robot-01/temperature" in seen
    snap = sim.snapshot_observations()
    assert snap["observations"]


def test_telemetry_bus_mqtt_helpers() -> None:
    bus = TelemetryBus()
    assert bus.mqtt_enabled is False
    assert bus.mqtt_endpoint is None
    assert bus.enable_mqtt("127.0.0.1", 9) is False
    assert bus.mqtt_enabled is False
    bus.disable_mqtt()


def test_live_api_health_and_spike(tmp_path: Path) -> None:
    app = create_app(
        example_dir=EXAMPLE,
        work_dir=tmp_path / "live",
        interval_seconds=60,
        autostart=False,
    )
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        body = health.json()
        assert body["status"] == "ok"
        assert body["mqtt"]["requested"] is False
        assert body["mqtt"]["enabled"] is False

        ready = client.get("/api/ready")
        assert ready.status_code == 200
        ready_body = ready.json()
        assert ready_body["status"] == "ready"
        assert ready_body["hasDriftReport"] is True

        twin = client.get("/api/twin")
        assert twin.status_code == 200
        body = twin.json()
        assert body["twin"]["name"] == "assembly-line-a"
        assert body["drift"] is not None

        spike = client.post("/api/simulate/spike")
        assert spike.status_code == 200
        assert spike.json()["drift"]["status"]["hasDrift"] is True

        reconcile = client.post("/api/reconcile")
        assert reconcile.status_code == 200
        body = reconcile.json()
        assert body["changes"] >= 1
        assert body["healed"]["robot_firmware"] == "4.14"
        assert body["healed"]["robot_status"] == "running"
        assert body["drift"]["status"]["hasDrift"] is False
        assert "scene" in body
        assert body["scene"]["protocol"]["name"] == "twinops.highlight.v1"

        proposal = client.get("/api/proposal/latest")
        assert proposal.status_code == 200
        assert proposal.json()["status"]["applied"] is True

        timeline = client.get("/api/timeline")
        assert timeline.status_code == 200
        types = {item["type"] for item in timeline.json()["items"]}
        assert "reconcile" in types
        assert len(timeline.json()["items"]) >= 1

        metrics = client.get("/api/metrics")
        assert metrics.status_code == 200
        assert "hasDrift" in metrics.json()
        prom = client.get("/metrics")
        assert prom.status_code == 200
        assert "twinops_drift_has_drift" in prom.text

        report = client.get("/api/drift/report")
        assert report.status_code == 200
        assert "text/html" in report.headers.get("content-type", "")
        assert "Drift" in report.text or "drift" in report.text

        csv_report = client.get("/api/drift/csv")
        assert csv_report.status_code == 200
        assert "text/csv" in csv_report.headers.get("content-type", "")
        assert "prim,attribute" in csv_report.text

        scene_html = client.get("/api/scene/report")
        assert scene_html.status_code == 200
        assert "text/html" in scene_html.headers.get("content-type", "")
        assert "Scene" in scene_html.text or "highlight" in scene_html.text.lower()

        topics = client.get("/api/mqtt/topics")
        assert topics.status_code == 200
        body = topics.json()
        assert body["kind"] == "MqttTopicCatalog"
        assert any(
            b["topic"] == "factory/robot-01/temperature" for b in body["spec"]["bindings"]
        )
