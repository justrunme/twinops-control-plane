"""Lightweight structural validation for twinops.highlight.v1 snapshots."""

from __future__ import annotations

from typing import Any

ALLOWED_STATUS = frozenset({"SYNCED", "WARNING", "MISSING", "DRIFT", "CRITICAL"})


def validate_scene_snapshot(scene: dict[str, Any]) -> list[str]:
    """Return a list of validation errors (empty means OK)."""
    errors: list[str] = []
    if not isinstance(scene, dict):
        return ["scene must be an object"]

    if not str(scene.get("twin") or "").strip():
        errors.append("twin is required")
    if "hasDrift" not in scene or not isinstance(scene.get("hasDrift"), bool):
        errors.append("hasDrift must be a boolean")

    protocol = scene.get("protocol")
    if not isinstance(protocol, dict):
        errors.append("protocol is required")
    elif protocol.get("name") != "twinops.highlight.v1":
        errors.append("protocol.name must be twinops.highlight.v1")

    prims = scene.get("prims")
    if not isinstance(prims, list):
        errors.append("prims must be an array")
        return errors

    for index, prim in enumerate(prims):
        prefix = f"prims[{index}]"
        if not isinstance(prim, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if not str(prim.get("prim") or "").strip():
            errors.append(f"{prefix}.prim is required")
        if not str(prim.get("label") or "").strip():
            errors.append(f"{prefix}.label is required")
        status = prim.get("status")
        if status not in ALLOWED_STATUS:
            errors.append(f"{prefix}.status invalid: {status!r}")
        highlight = prim.get("highlight")
        if not isinstance(highlight, dict):
            errors.append(f"{prefix}.highlight is required")
            continue
        if not isinstance(highlight.get("enabled"), bool):
            errors.append(f"{prefix}.highlight.enabled must be bool")
        color = highlight.get("color")
        if not isinstance(color, list) or len(color) != 3:
            errors.append(f"{prefix}.highlight.color must be [r,g,b]")
        intensity = highlight.get("intensity")
        if not isinstance(intensity, (int, float)) or intensity < 0:
            errors.append(f"{prefix}.highlight.intensity must be >= 0")
    return errors


def assert_valid_scene_snapshot(scene: dict[str, Any]) -> None:
    errors = validate_scene_snapshot(scene)
    if errors:
        raise ValueError("invalid twinops.highlight.v1: " + "; ".join(errors))
