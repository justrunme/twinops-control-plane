"""Verify a reconciliation apply by rebuilding the stage and re-running drift."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from twinops.composer import compose_digital_twin
from twinops.drift.engine import detect_drift
from twinops.schema import load_manifest


@dataclass
class VerifyResult:
    stage_root: Path
    overlay_path: Path
    has_drift: bool
    summary: dict[str, Any]
    findings: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": "twinops.io/v1alpha1",
            "kind": "ReconciliationVerify",
            "spec": {
                "stageRoot": str(self.stage_root),
                "overlay": str(self.overlay_path),
            },
            "status": {
                "hasDrift": self.has_drift,
                "summary": self.summary,
                "findings": self.findings,
                "ok": not self.has_drift,
            },
        }


def _inject_overlay(stage_dir: Path, overlay_src: Path) -> Path:
    """Copy reconcile overlay into a composed stage and reference it from root.usda."""
    target = stage_dir / "reconcile-overlay.usda"
    shutil.copy2(overlay_src, target)
    root = stage_dir / "root.usda"
    root_text = root.read_text(encoding="utf-8")
    if "reconcile-overlay.usda" not in root_text:
        if "subLayers = [" in root_text:
            root_text = root_text.replace(
                "    subLayers = [\n",
                "    subLayers = [\n        @./reconcile-overlay.usda@\n",
                1,
            )
        else:
            # Fallback: prepend a minimal subLayers block after header.
            root_text = root_text.replace(
                "#usda 1.0\n",
                "#usda 1.0\n(\n    subLayers = [\n        @./reconcile-overlay.usda@\n    ]\n)\n",
                1,
            )
        root.write_text(root_text, encoding="utf-8")
    return target


def verify_apply(
    *,
    manifest: str | Path,
    desired: str | Path,
    observed: str | Path,
    overlay: str | Path,
    stage_out: str | Path,
) -> VerifyResult:
    """Compose the twin, inject the applied overlay, and re-evaluate drift."""
    manifest_path = Path(manifest)
    twin = load_manifest(manifest_path)
    out = Path(stage_out).resolve()
    if out.exists():
        shutil.rmtree(out)
    composed = compose_digital_twin(twin, out)
    if not composed.ok:
        raise RuntimeError("compose failed during apply verification")
    overlay_path = _inject_overlay(out, Path(overlay))
    report = detect_drift(
        desired=desired,
        stage=composed.files["root"],
        observed=observed,
        manifest=manifest_path,
    )
    return VerifyResult(
        stage_root=composed.files["root"],
        overlay_path=overlay_path,
        has_drift=report.has_drift,
        summary=dict(report.summary),
        findings=len(report.findings),
    )
