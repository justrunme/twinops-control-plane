from pathlib import Path

from fastapi.testclient import TestClient
from twinops.api.app import create_app
from twinops.scene import build_scene_snapshot

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def test_build_scene_snapshot_aggregates_worst_status() -> None:
    scene = build_scene_snapshot(
        twin_name="assembly-line-a",
        findings=[
            {
                "prim": "/World/Factory/LineA/Robot01",
                "attribute": "twinops:temperature",
                "status": "WARNING",
                "severity": "medium",
                "message": "warm",
            },
            {
                "prim": "/World/Factory/LineA/Robot01",
                "attribute": "twinops:status",
                "status": "CRITICAL",
                "severity": "high",
                "message": "overheating",
            },
        ],
        generated_at="2026-07-31T00:00:00Z",
    )
    assert scene["hasDrift"] is True
    assert scene["protocol"]["name"] == "twinops.highlight.v1"
    robot = next(item for item in scene["prims"] if item["label"] == "Robot01")
    assert robot["status"] == "CRITICAL"
    assert robot["highlight"]["enabled"] is True
    assert len(robot["findings"]) == 2


def test_api_scene_endpoint(tmp_path: Path) -> None:
    app = create_app(
        example_dir=EXAMPLE,
        work_dir=tmp_path / "live",
        interval_seconds=60,
        autostart=False,
    )
    with TestClient(app) as client:
        scene = client.get("/api/scene")
        assert scene.status_code == 200
        body = scene.json()
        assert body["twin"] == "assembly-line-a"
        assert "prims" in body
        assert any(item["label"] == "Robot01" for item in body["prims"])

        spike = client.post("/api/simulate/spike")
        assert spike.status_code == 200
        after = client.get("/api/scene").json()
        robot = next(item for item in after["prims"] if item["label"] == "Robot01")
        assert robot["highlight"]["enabled"] is True
        assert robot["status"] in {"DRIFT", "CRITICAL", "WARNING", "MISSING"}
