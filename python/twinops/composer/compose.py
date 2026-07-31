"""Compose OpenUSD layers from a DigitalTwin manifest."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from twinops import __version__
from twinops.composer import usda
from twinops.schema.manifest import DigitalTwinManifest
from twinops.validate.report import ValidationIssue, validate_build


@dataclass
class BuildResult:
    output_dir: Path
    files: dict[str, Path]
    report: dict[str, Any]
    issues: list[ValidationIssue]

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


def compose_digital_twin(
    manifest: DigitalTwinManifest,
    output_dir: str | Path,
    *,
    copy_base_stage: bool = True,
) -> BuildResult:
    """Generate USD overlays and a reconciliation report for a DigitalTwin."""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    base_stage = manifest.resolve_base_stage()
    base_text = base_stage.read_text(encoding="utf-8")

    warnings: list[str] = []
    known_variants = usda.discover_variant_names(base_text, manifest.variant_set)
    if known_variants and manifest.variant not in known_variants:
        warnings.append(
            f"variant '{manifest.variant}' not found in base stage "
            f"variantSet '{manifest.variant_set}' "
            f"(known: {', '.join(sorted(known_variants))})"
        )

    plm_items: list[tuple[str, str, Any]] = []
    for mapping in manifest.plm_mappings:
        plm_items.extend(
            [
                (mapping.prim, "twinops:plmItemId", mapping.item_id),
                (mapping.prim, "twinops:plmRevision", mapping.revision),
                (mapping.prim, "twinops:lifecycle", mapping.lifecycle),
                (mapping.prim, "twinops:plmProvider", manifest.plm_provider),
            ]
        )
    plm_layer = usda.build_overlay_layer(
        doc=f"TwinOps PLM overlay for {manifest.name}",
        prims=usda.group_attributes_by_prim(plm_items),
    )

    telemetry_items: list[tuple[str, str, Any]] = []
    for mapping in manifest.telemetry_mappings:
        attr_name = mapping.attribute
        if not attr_name.startswith("twinops:"):
            attr_name = f"twinops:{attr_name}"
        default = mapping.default
        if default is None:
            default = "" if attr_name.endswith(("status", "firmware")) else 0.0
        # Per-attribute topic binding so multiple sensors on one prim do not collide.
        short = attr_name.removeprefix("twinops:")
        topic_attr = f"twinops:{short}Topic"
        telemetry_items.append((mapping.prim, topic_attr, mapping.topic))
        telemetry_items.append((mapping.prim, attr_name, default))
        telemetry_items.append(
            (mapping.prim, "twinops:telemetryProvider", manifest.telemetry_provider)
        )
        if manifest.telemetry_endpoint:
            telemetry_items.append(
                (mapping.prim, "twinops:telemetryEndpoint", manifest.telemetry_endpoint)
            )
    telemetry_layer = usda.build_overlay_layer(
        doc=f"TwinOps telemetry overlay for {manifest.name}",
        prims=usda.group_attributes_by_prim(telemetry_items),
    )

    variant_layer = usda.build_variant_overlay(
        variant_prim=manifest.variant_prim,
        variant_set=manifest.variant_set,
        variant=manifest.variant,
    )

    base_ref: str
    files: dict[str, Path] = {}
    if copy_base_stage:
        assets_dir = out / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        copied = assets_dir / base_stage.name
        shutil.copy2(base_stage, copied)
        files["base_stage"] = copied
        base_ref = f"./assets/{base_stage.name}"
    else:
        # Relative path from output dir back to the original base stage.
        base_ref = Path(
            Path.cwd() / base_stage if not base_stage.is_absolute() else base_stage
        ).resolve().as_posix()
        try:
            base_ref = Path(base_ref).resolve().relative_to(out).as_posix()
        except ValueError:
            base_ref = Path(base_ref).resolve().as_uri()

    root_layer = usda.build_root_stage(
        doc=f"TwinOps composed stage for {manifest.name}",
        sublayers=[
            "./variant-overlay.usda",
            "./telemetry-overlay.usda",
            "./plm-overlay.usda",
            base_ref,
        ],
    )

    files["plm_overlay"] = out / "plm-overlay.usda"
    files["telemetry_overlay"] = out / "telemetry-overlay.usda"
    files["variant_overlay"] = out / "variant-overlay.usda"
    files["root"] = out / "root.usda"

    files["plm_overlay"].write_text(plm_layer, encoding="utf-8")
    files["telemetry_overlay"].write_text(telemetry_layer, encoding="utf-8")
    files["variant_overlay"].write_text(variant_layer, encoding="utf-8")
    files["root"].write_text(root_layer, encoding="utf-8")

    report = {
        "apiVersion": "twinops.io/v1alpha1",
        "kind": "ReconciliationReport",
        "metadata": {
            "name": manifest.name,
            "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "generator": "twinopsctl",
            "generatorVersion": __version__,
        },
        "spec": {
            "variant": {
                "set": manifest.variant_set,
                "name": manifest.variant,
                "prim": manifest.variant_prim,
            },
            "plm": {
                "provider": manifest.plm_provider,
                "mappings": len(manifest.plm_mappings),
            },
            "telemetry": {
                "provider": manifest.telemetry_provider,
                "endpoint": manifest.telemetry_endpoint,
                "mappings": len(manifest.telemetry_mappings),
            },
            "streaming": {
                "enabled": manifest.streaming.enabled,
                "gpuClass": manifest.streaming.gpu_class,
                "idleTimeout": manifest.streaming.idle_timeout,
            },
            "policyThresholds": len(manifest.thresholds),
        },
        "status": {
            "phase": "Composed",
            "baseStage": str(base_stage),
            "outputDir": str(out),
            "artifacts": {key: str(path) for key, path in files.items()},
            "warnings": warnings,
            "notes": [
                "GPU / Omniverse runtime not required for composition",
                "Drift engine is planned for Milestone 2",
            ],
        },
    }

    report_path = out / "reconciliation-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    files["report"] = report_path

    issues = validate_build(manifest, files, warnings=warnings)
    if any(issue.severity == "error" for issue in issues):
        report["status"]["phase"] = "Failed"
    elif warnings:
        report["status"]["phase"] = "ComposedWithWarnings"
    report["status"]["validation"] = [
        {"severity": i.severity, "code": i.code, "message": i.message} for i in issues
    ]
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    return BuildResult(output_dir=out, files=files, report=report, issues=issues)
