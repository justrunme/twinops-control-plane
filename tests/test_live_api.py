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

        proposal = client.get("/api/proposal/latest")
        assert proposal.status_code == 200
        assert proposal.json()["status"]["applied"] is True

        timeline = client.get("/api/timeline")
        assert timeline.status_code == 200
        types = {item["type"] for item in timeline.json()["items"]}
        assert "reconcile" in types
        assert len(timeline.json()["items"]) >= 1
