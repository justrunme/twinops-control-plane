"""Highlight apply backends: plan (CI), USD overlay (no Kit), Kit USD (Omniverse)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from twinops_highlight.client import HighlightTarget, format_highlight_plan


@runtime_checkable
class HighlightApplier(Protocol):
    def apply(self, targets: list[HighlightTarget]) -> list[str]: ...

    def clear(self) -> list[str]: ...


@dataclass
class PlanApplier:
    """CI/demo backend — prints the highlight plan only."""

    def apply(self, targets: list[HighlightTarget]) -> list[str]:
        if not targets:
            return ["CLEAR — no drifted prims"]
        return [format_highlight_plan(target) for target in targets]

    def clear(self) -> list[str]:
        return ["CLEAR — all highlights removed"]


@dataclass
class UsdOverlayApplier:
    """Write a TwinOps highlight overlay USDA (works without Omniverse/pxr)."""

    output_path: Path

    def apply(self, targets: list[HighlightTarget]) -> list[str]:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from twinops.composer.usda import PrimSpec, build_overlay_layer
        except ImportError:
            text = _minimal_overlay(targets)
            self.output_path.write_text(text, encoding="utf-8")
            return [f"WROTE overlay {self.output_path} targets={len(targets)}"]

        prims: list[PrimSpec] = []
        for target in targets:
            r, g, b = (target.color + [0.86, 0.15, 0.15])[:3]
            prims.append(
                PrimSpec(
                    path=target.prim,
                    attributes={
                        "twinops:driftStatus": target.status,
                        "twinops:highlightIntensity": float(target.intensity),
                        "twinops:highlightColor": f"{r:.4f},{g:.4f},{b:.4f}",
                    },
                )
            )
        text = build_overlay_layer(
            doc="TwinOps highlight overlay (runtime)",
            prims=prims,
        )
        self.output_path.write_text(text, encoding="utf-8")
        return [f"WROTE overlay {self.output_path} targets={len(targets)}"] + [
            format_highlight_plan(t) for t in targets
        ]

    def clear(self) -> list[str]:
        return self.apply([])


class KitUsdApplier:
    """Apply highlights inside Omniverse Kit via omni.usd (optional dependency)."""

    def __init__(self) -> None:
        self._last_prims: list[str] = []

    def apply(self, targets: list[HighlightTarget]) -> list[str]:
        try:
            import omni.usd  # type: ignore
            from pxr import Gf, Sdf, UsdGeom  # type: ignore
        except ImportError:
            return PlanApplier().apply(targets)

        ctx = omni.usd.get_context()
        stage = ctx.get_stage() if ctx is not None else None
        if stage is None:
            return ["KIT — no stage open; falling back to plan"] + PlanApplier().apply(
                targets
            )

        notes: list[str] = []
        for prim_path in self._last_prims:
            prim = stage.GetPrimAtPath(prim_path)
            if prim and prim.IsValid():
                imageable = UsdGeom.Gprim(prim)
                if imageable:
                    attr = imageable.GetDisplayColorAttr()
                    if attr:
                        attr.Clear()

        selection: list[str] = []
        for target in targets:
            prim = stage.GetPrimAtPath(target.prim)
            if not prim or not prim.IsValid():
                notes.append(f"KIT MISS {target.prim}")
                continue
            imageable = UsdGeom.Gprim(prim)
            if imageable:
                color = Gf.Vec3f(*((target.color + [0.86, 0.15, 0.15])[:3]))
                imageable.GetDisplayColorAttr().Set([color])
            prim.CreateAttribute(
                "twinops:driftStatus", Sdf.ValueTypeNames.String
            ).Set(target.status)
            prim.CreateAttribute(
                "twinops:highlightIntensity", Sdf.ValueTypeNames.Float
            ).Set(float(target.intensity))
            selection.append(target.prim)
            notes.append(f"KIT SET {target.prim} status={target.status}")

        self._last_prims = selection
        try:
            import omni.kit.commands  # type: ignore

            if selection:
                omni.kit.commands.execute(
                    "SelectPrimsCommand",
                    old_selected_paths=[],
                    new_selected_paths=selection,
                    expand_in_stage=True,
                )
        except Exception:  # noqa: BLE001 - selection is optional
            notes.append("KIT — selection command unavailable")
        return notes or ["KIT — no valid prims"]

    def clear(self) -> list[str]:
        return self.apply([])


def _minimal_overlay(targets: list[HighlightTarget]) -> str:
    lines = [
        "#usda 1.0",
        "(",
        '    doc = "TwinOps highlight overlay (runtime)"',
        ")",
        "",
    ]
    for target in targets:
        name = target.prim.lstrip("/").split("/")[-1]
        lines.extend(
            [
                f'over "{name}"',
                "{",
                f'    custom string twinops:driftStatus = "{target.status}"',
                "}",
                "",
            ]
        )
    return "\n".join(lines)


def select_applier(
    *,
    mode: str = "auto",
    overlay_path: str | Path | None = None,
) -> HighlightApplier:
    """Pick apply backend: auto prefers Kit, then overlay path, else plan."""
    mode = (mode or "auto").strip().lower()
    if mode == "plan":
        return PlanApplier()
    if mode == "overlay":
        return UsdOverlayApplier(
            output_path=Path(overlay_path or "/tmp/twinops-highlight-overlay.usda")
        )
    if mode == "kit":
        return KitUsdApplier()
    try:
        import omni.usd  # type: ignore  # noqa: F401

        return KitUsdApplier()
    except ImportError:
        if overlay_path:
            return UsdOverlayApplier(output_path=Path(overlay_path))
        return PlanApplier()
