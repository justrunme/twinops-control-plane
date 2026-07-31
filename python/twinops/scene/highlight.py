"""Build a GPU-agnostic scene highlight snapshot from drift findings.

Consumers (web UI, Omniverse Kit extension, streaming clients) poll /api/scene
and apply selection / emissive highlight to drifted prims. No Omniverse runtime
is required to produce or validate this payload.
"""

from __future__ import annotations

from typing import Any

STATUS_RANK = {
    "SYNCED": 0,
    "WARNING": 1,
    "MISSING": 2,
    "DRIFT": 3,
    "CRITICAL": 4,
}

# Rough sRGB colors for Kit-style emissive highlights.
HIGHLIGHT_COLORS: dict[str, list[float]] = {
    "SYNCED": [0.12, 0.62, 0.33],
    "WARNING": [0.85, 0.47, 0.02],
    "MISSING": [0.39, 0.45, 0.55],
    "DRIFT": [0.86, 0.15, 0.15],
    "CRITICAL": [0.5, 0.11, 0.11],
}

DEFAULT_ASSEMBLY_PRIMS = (
    "/World/Factory/LineA",
    "/World/Factory/LineA/Robot01",
    "/World/Factory/LineA/Conveyor01",
    "/World/Factory/LineA/Scanner01",
    "/World/Factory/LineA/Packaging01",
)


def _short_label(prim: str) -> str:
    return prim.rsplit("/", 1)[-1] or prim


def _worst_status(statuses: list[str]) -> str:
    if not statuses:
        return "SYNCED"
    return max(statuses, key=lambda status: STATUS_RANK.get(status, 0))


def build_scene_snapshot(
    *,
    twin_name: str,
    findings: list[dict[str, Any]],
    generated_at: str | None = None,
    base_prims: tuple[str, ...] | list[str] = DEFAULT_ASSEMBLY_PRIMS,
    protocol_version: str = "twinops.highlight.v1",
) -> dict[str, Any]:
    """Aggregate findings into a prim-centric highlight tree."""
    by_prim: dict[str, list[dict[str, Any]]] = {prim: [] for prim in base_prims}

    for finding in findings:
        prim = str(finding.get("prim") or "")
        if not prim:
            continue
        by_prim.setdefault(prim, []).append(finding)

    prims: list[dict[str, Any]] = []
    for prim in sorted(by_prim.keys()):
        items = by_prim[prim]
        status = _worst_status([str(item.get("status") or "SYNCED") for item in items])
        intensity = min(1.0, 0.35 + 0.2 * STATUS_RANK.get(status, 0))
        prims.append(
            {
                "prim": prim,
                "label": _short_label(prim),
                "status": status,
                "highlight": {
                    "enabled": status != "SYNCED",
                    "color": HIGHLIGHT_COLORS.get(status, HIGHLIGHT_COLORS["DRIFT"]),
                    "intensity": intensity if status != "SYNCED" else 0.0,
                },
                "findings": [
                    {
                        "attribute": item.get("attribute"),
                        "status": item.get("status"),
                        "severity": item.get("severity"),
                        "message": item.get("message"),
                        "desired": item.get("desired"),
                        "rendered": item.get("rendered"),
                        "observed": item.get("observed"),
                    }
                    for item in items
                ],
            }
        )

    has_drift = any(item["status"] != "SYNCED" for item in prims)
    return {
        "twin": twin_name,
        "generatedAt": generated_at,
        "hasDrift": has_drift,
        "prims": prims,
        "protocol": {
            "name": protocol_version,
            "description": (
                "Poll this snapshot and apply selection/emissive highlight to "
                "prims where highlight.enabled is true."
            ),
        },
    }
