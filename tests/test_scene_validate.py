"""Tests for twinops.highlight.v1 validation."""

from __future__ import annotations

from twinops.scene import build_scene_snapshot, validate_scene_snapshot


def test_valid_built_snapshot() -> None:
    scene = build_scene_snapshot(
        twin_name="assembly-line-a",
        findings=[
            {
                "prim": "/World/Factory/LineA/Robot01",
                "attribute": "twinops:temperature",
                "status": "CRITICAL",
                "severity": "critical",
                "message": "hot",
            }
        ],
        generated_at="2026-07-31T00:00:00Z",
    )
    assert validate_scene_snapshot(scene) == []


def test_invalid_protocol_name() -> None:
    scene = build_scene_snapshot(twin_name="t", findings=[])
    scene["protocol"]["name"] = "wrong"
    errors = validate_scene_snapshot(scene)
    assert any("protocol.name" in err for err in errors)
