"""Compare desired, rendered, and observed digital-twin state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from twinops.drift.loaders import (
    DriftLoadError,
    extract_rendered_attributes,
    load_desired_state,
    load_observed_state,
)
from twinops.drift.model import (
    STATUS_ORDER,
    DesiredState,
    DriftFinding,
    ObservedState,
    PolicyThreshold,
    display_value,
    normalize_attr,
)
from twinops.schema.manifest import DigitalTwinManifest, load_manifest


@dataclass
class DriftReport:
    name: str
    findings: list[DriftFinding] = field(default_factory=list)
    generated_at: str = ""
    desired_path: str = ""
    stage_path: str = ""
    observed_path: str = ""
    summary: dict[str, int] = field(default_factory=dict)

    @property
    def has_drift(self) -> bool:
        return any(item.status in {"DRIFT", "CRITICAL", "MISSING"} for item in self.findings)

    @property
    def exit_code(self) -> int:
        if any(item.status == "CRITICAL" for item in self.findings):
            return 3
        if any(item.status in {"DRIFT", "MISSING"} for item in self.findings):
            return 1
        if any(item.status == "WARNING" for item in self.findings):
            return 0
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": "twinops.io/v1alpha1",
            "kind": "DriftReport",
            "metadata": {
                "name": self.name,
                "generatedAt": self.generated_at,
            },
            "spec": {
                "desired": self.desired_path,
                "stage": self.stage_path,
                "observed": self.observed_path,
            },
            "status": {
                "summary": self.summary,
                "hasDrift": self.has_drift,
                "findings": [
                    {
                        "prim": f.prim,
                        "attribute": f.attribute,
                        "desired": f.desired,
                        "rendered": f.rendered,
                        "observed": f.observed,
                        "status": f.status,
                        "severity": f.severity,
                        "message": f.message,
                    }
                    for f in self.findings
                ],
            },
        }


def detect_drift(
    *,
    desired: str | Path | DesiredState,
    stage: str | Path | dict[str, dict[str, Any]],
    observed: str | Path | ObservedState,
    manifest: str | Path | DigitalTwinManifest | None = None,
) -> DriftReport:
    desired_state = (
        desired if isinstance(desired, DesiredState) else load_desired_state(desired)
    )
    observed_state = (
        observed if isinstance(observed, ObservedState) else load_observed_state(observed)
    )
    rendered = (
        stage if isinstance(stage, dict) else extract_rendered_attributes(stage)
    )

    thresholds: list[PolicyThreshold] = []
    twin_name = desired_state.name
    if manifest is not None:
        loaded = manifest if isinstance(manifest, DigitalTwinManifest) else load_manifest(manifest)
        twin_name = loaded.name
        thresholds = [
            PolicyThreshold(
                prim=item.prim,
                attribute=normalize_attr(item.attribute),
                warn_above=item.warn_above,
                critical_above=item.critical_above,
            )
            for item in loaded.thresholds
        ]

    findings: list[DriftFinding] = []
    prims = sorted(
        set(desired_state.by_prim())
        | set(rendered)
        | set(observed_state.attributes_by_prim)
    )

    for prim in prims:
        desired_attrs = desired_state.by_prim().get(prim)
        rendered_attrs = rendered.get(prim, {})
        observed_attrs = observed_state.attributes_by_prim.get(prim, {})

        attr_names = sorted(
            set(desired_attrs.attributes if desired_attrs else {})
            | {
                key
                for key in rendered_attrs
                if key
                in {
                    "twinops:plmRevision",
                    "twinops:firmware",
                    "twinops:status",
                    "twinops:temperature",
                    "twinops:speed",
                    "twinops:lifecycle",
                }
                or key in (desired_attrs.attributes if desired_attrs else {})
            }
            | set(observed_attrs)
        )

        # Always compare core industrial identity attrs when present on any side.
        for attr in attr_names:
            if attr.endswith("Topic") or attr in {
                "twinops:telemetryProvider",
                "twinops:telemetryEndpoint",
                "twinops:plmProvider",
                "twinops:assetClass",
                "twinops:role",
                "twinops:opsMode",
                "twinops:targetCycleTime",
                "twinops:selectedVariant",
            }:
                continue

            desired_value = (
                desired_attrs.attributes.get(attr) if desired_attrs else None
            )
            rendered_value = rendered_attrs.get(attr)
            observed_value = observed_attrs.get(attr)

            # Skip pure rendered metadata with no desired/observed signal.
            if desired_value is None and observed_value is None:
                continue

            finding = _compare_values(
                prim=prim,
                attribute=attr,
                desired=desired_value,
                rendered=rendered_value,
                observed=observed_value,
            )
            if finding:
                findings.append(finding)

        if desired_attrs and not observed_attrs:
            findings.append(
                DriftFinding(
                    prim=prim,
                    attribute="telemetry",
                    desired="present",
                    rendered="n/a",
                    observed=None,
                    status="MISSING",
                    severity="medium",
                    message="telemetry unavailable for desired resource",
                )
            )

        for threshold in thresholds:
            if threshold.prim != prim:
                continue
            observed_value = observed_attrs.get(threshold.attribute)
            if observed_value is None:
                continue
            try:
                numeric = float(observed_value)
            except (TypeError, ValueError):
                continue
            if (
                threshold.critical_above is not None
                and numeric > threshold.critical_above
            ):
                findings.append(
                    DriftFinding(
                        prim=prim,
                        attribute=threshold.attribute,
                        desired=f"<= {threshold.critical_above}",
                        rendered=rendered_attrs.get(threshold.attribute),
                        observed=numeric,
                        status="CRITICAL",
                        severity="high",
                        message=(
                            f"{threshold.attribute} {display_value(numeric)} exceeds "
                            f"critical threshold {threshold.critical_above}"
                        ),
                    )
                )
            elif threshold.warn_above is not None and numeric > threshold.warn_above:
                findings.append(
                    DriftFinding(
                        prim=prim,
                        attribute=threshold.attribute,
                        desired=f"<= {threshold.warn_above}",
                        rendered=rendered_attrs.get(threshold.attribute),
                        observed=numeric,
                        status="WARNING",
                        severity="medium",
                        message=(
                            f"{threshold.attribute} {display_value(numeric)} exceeds "
                            f"warning threshold {threshold.warn_above}"
                        ),
                    )
                )

    findings.sort(
        key=lambda item: (
            -STATUS_ORDER.get(item.status, 0),
            item.prim,
            item.attribute,
        )
    )
    summary: dict[str, int] = {}
    for item in findings:
        summary[item.status] = summary.get(item.status, 0) + 1

    return DriftReport(
        name=twin_name,
        findings=findings,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        desired_path=str(desired) if not isinstance(desired, DesiredState) else "",
        stage_path=str(stage) if not isinstance(stage, dict) else "",
        observed_path=str(observed) if not isinstance(observed, ObservedState) else "",
        summary=summary,
    )


def _compare_values(
    *,
    prim: str,
    attribute: str,
    desired: Any,
    rendered: Any,
    observed: Any,
) -> DriftFinding | None:
    def eq(left: Any, right: Any) -> bool:
        if left is None or right is None:
            return False
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return abs(float(left) - float(right)) < 1e-6
        return str(left) == str(right)

    if desired is not None and observed is None and rendered is None:
        return DriftFinding(
            prim=prim,
            attribute=attribute,
            desired=desired,
            rendered=None,
            observed=None,
            status="MISSING",
            severity="medium",
            message="desired attribute missing from rendered stage and observations",
        )

    mismatches: list[str] = []
    if desired is not None and rendered is not None and not eq(desired, rendered):
        mismatches.append("desired≠rendered")
    if desired is not None and observed is not None and not eq(desired, observed):
        mismatches.append("desired≠observed")
    if (
        rendered is not None
        and observed is not None
        and desired is None
        and not eq(rendered, observed)
    ):
        mismatches.append("rendered≠observed")
    if desired is not None and rendered is None and observed is not None and not eq(
        desired, observed
    ):
        mismatches.append("desired≠observed")

    # If desired and rendered match but observed differs — classic physical drift.
    if (
        desired is not None
        and rendered is not None
        and eq(desired, rendered)
        and observed is not None
        and not eq(desired, observed)
    ):
        mismatches = ["desired/rendered≠observed"]

    if not mismatches:
        # Only emit SYNCED rows for explicitly desired attributes.
        if desired is None:
            return None
        return DriftFinding(
            prim=prim,
            attribute=attribute,
            desired=desired,
            rendered=rendered,
            observed=observed,
            status="SYNCED",
            severity="low",
            message="desired, rendered and observed agree",
        )

    return DriftFinding(
        prim=prim,
        attribute=attribute,
        desired=desired,
        rendered=rendered,
        observed=observed,
        status="DRIFT",
        severity="high",
        message="; ".join(mismatches),
    )


def save_drift_report(report: DriftReport, path: str | Path) -> Path:
    import json

    out = Path(path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


# Re-export for callers that catch loader errors through engine.
__all__ = ["DriftReport", "detect_drift", "save_drift_report", "DriftLoadError"]
