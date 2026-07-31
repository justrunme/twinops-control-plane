"""Validate composed TwinOps artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from twinops.schema.manifest import DigitalTwinManifest


@dataclass(frozen=True)
class ValidationIssue:
    severity: str  # error | warning | info
    code: str
    message: str


def validate_build(
    manifest: DigitalTwinManifest,
    files: dict[str, Path],
    *,
    warnings: list[str] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    required = ("root", "plm_overlay", "telemetry_overlay", "variant_overlay", "report")
    for key in required:
        path = files.get(key)
        if path is None or not path.is_file():
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="missing_artifact",
                    message=f"required artifact '{key}' was not generated",
                )
            )
            continue
        text = path.read_text(encoding="utf-8")
        if key.endswith("overlay") or key == "root":
            if not text.startswith("#usda 1.0"):
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="invalid_usda",
                        message=f"{path.name} is not valid USDA ASCII",
                    )
                )
            if len(text.strip()) < 20:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="empty_usda",
                        message=f"{path.name} appears empty",
                    )
                )

    root = files.get("root")
    if root and root.is_file():
        root_text = root.read_text(encoding="utf-8")
        for layer_name in (
            "variant-overlay.usda",
            "telemetry-overlay.usda",
            "plm-overlay.usda",
        ):
            if layer_name not in root_text:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="missing_sublayer",
                        message=f"root stage does not reference {layer_name}",
                    )
                )

    plm_overlay = files.get("plm_overlay")
    if plm_overlay and plm_overlay.is_file() and manifest.plm_mappings:
        text = plm_overlay.read_text(encoding="utf-8")
        for mapping in manifest.plm_mappings:
            leaf = mapping.prim.rsplit("/", 1)[-1]
            if leaf not in text:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="missing_plm_prim",
                        message=f"PLM overlay missing prim leaf '{leaf}'",
                    )
                )
            if mapping.item_id not in text:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="missing_plm_item",
                        message=f"PLM overlay missing itemId '{mapping.item_id}'",
                    )
                )

    for warning in warnings or []:
        issues.append(
            ValidationIssue(severity="warning", code="compose_warning", message=warning)
        )

    if not manifest.plm_mappings:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="no_plm_mappings",
                message="manifest has no PLM mappings",
            )
        )

    if not issues:
        issues.append(
            ValidationIssue(
                severity="info",
                code="ok",
                message="composition validated successfully",
            )
        )

    return issues
