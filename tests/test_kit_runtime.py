"""Tests for TwinOps Kit scene runtime apply backends (no Omniverse required)."""

from __future__ import annotations

from pathlib import Path

from twinops_highlight.apply import PlanApplier, UsdOverlayApplier, select_applier
from twinops_highlight.client import HighlightTarget
from twinops_highlight.runtime import TwinOpsSceneRuntime


def test_plan_applier_clear_and_apply() -> None:
    applier = PlanApplier()
    assert "CLEAR" in applier.clear()[0]
    notes = applier.apply(
        [
            HighlightTarget(
                prim="/World/Factory/LineA/Robot01",
                status="CRITICAL",
                color=[0.8, 0.1, 0.1],
                intensity=1.0,
                message="hot",
            )
        ]
    )
    assert any("HIGHLIGHT" in line for line in notes)


def test_usd_overlay_applier_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "highlight.usda"
    applier = UsdOverlayApplier(output_path=out)
    applier.apply(
        [
            HighlightTarget(
                prim="/World/Factory/LineA/Robot01",
                status="DRIFT",
                color=[0.5, 0.1, 0.1],
                intensity=0.9,
                message="",
            )
        ]
    )
    text = out.read_text(encoding="utf-8")
    assert "#usda 1.0" in text
    assert "twinops:driftStatus" in text
    assert "Robot01" in text


def test_select_applier_overlay_mode(tmp_path: Path) -> None:
    path = tmp_path / "o.usda"
    applier = select_applier(mode="overlay", overlay_path=path)
    assert isinstance(applier, UsdOverlayApplier)


def test_runtime_tick_with_mocked_client(tmp_path: Path) -> None:
    class _Client:
        def fetch_scene(self):
            return {
                "twin": "assembly-line-a",
                "hasDrift": True,
                "prims": [
                    {
                        "prim": "/World/Factory/LineA/Robot01",
                        "status": "CRITICAL",
                        "highlight": {
                            "enabled": True,
                            "color": [0.8, 0.1, 0.1],
                            "intensity": 1.0,
                        },
                        "findings": [{"message": "hot"}],
                    }
                ],
            }

        def highlight_targets(self, scene=None):
            return TwinOpsHighlightClient().highlight_targets(scene or self.fetch_scene())

    from twinops_highlight.client import TwinOpsHighlightClient

    runtime = TwinOpsSceneRuntime(
        _Client(),  # type: ignore[arg-type]
        apply_mode="overlay",
        overlay_path=str(tmp_path / "rt.usda"),
    )
    tick = runtime.tick()
    assert tick.has_drift is True
    assert tick.targets == 1
    assert (tmp_path / "rt.usda").is_file()
