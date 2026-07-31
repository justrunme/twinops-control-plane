"""YAML DigitalTwin manifest loader and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_API_VERSIONS = {"twinops.io/v1alpha1"}
SUPPORTED_KINDS = {"DigitalTwin"}


class ManifestError(ValueError):
    """Raised when a DigitalTwin manifest is invalid."""


@dataclass(frozen=True)
class TelemetryMapping:
    topic: str
    prim: str
    attribute: str
    default: Any | None = None


@dataclass(frozen=True)
class PlmMapping:
    item_id: str
    prim: str
    revision: str = "A"
    lifecycle: str = "Released"


@dataclass(frozen=True)
class Threshold:
    prim: str
    attribute: str
    warn_above: float | None = None
    critical_above: float | None = None


@dataclass(frozen=True)
class StreamingSpec:
    enabled: bool = False
    gpu_class: str = "graphics"
    idle_timeout: str = "20m"


@dataclass
class DigitalTwinManifest:
    name: str
    base_stage: str
    variant: str = "nominal"
    variant_set: str = "ops"
    variant_prim: str = "/World/Factory/LineA"
    telemetry_provider: str = "mqtt"
    telemetry_endpoint: str = ""
    telemetry_mappings: list[TelemetryMapping] = field(default_factory=list)
    plm_provider: str = "mock"
    plm_mappings: list[PlmMapping] = field(default_factory=list)
    thresholds: list[Threshold] = field(default_factory=list)
    streaming: StreamingSpec = field(default_factory=StreamingSpec)
    labels: dict[str, str] = field(default_factory=dict)
    source_path: Path | None = None

    @property
    def manifest_dir(self) -> Path:
        if self.source_path is None:
            raise ManifestError("manifest source path is not set")
        return self.source_path.parent

    def resolve_base_stage(self) -> Path:
        base = Path(self.base_stage)
        if base.is_absolute():
            path = base
        else:
            path = (self.manifest_dir / base).resolve()
        if not path.is_file():
            raise ManifestError(f"base stage not found: {path}")
        return path


def _require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ManifestError(f"missing or invalid '{key}' object")
    return value


def _require_str(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{context}: '{key}' must be a non-empty string")
    return value.strip()


def _validate_prim(prim: str, context: str) -> str:
    if not prim.startswith("/") or prim.endswith("/") or "//" in prim:
        raise ManifestError(f"{context}: invalid prim path '{prim}'")
    return prim


def load_manifest(path: str | Path) -> DigitalTwinManifest:
    """Load and validate a DigitalTwin YAML manifest."""
    manifest_path = Path(path).resolve()
    if not manifest_path.is_file():
        raise ManifestError(f"manifest not found: {manifest_path}")

    with manifest_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be a mapping")

    api_version = raw.get("apiVersion")
    kind = raw.get("kind")
    if api_version not in SUPPORTED_API_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_API_VERSIONS))
        raise ManifestError(
            f"unsupported apiVersion '{api_version}', expected one of: {supported}"
        )
    if kind not in SUPPORTED_KINDS:
        raise ManifestError(f"unsupported kind '{kind}', expected DigitalTwin")

    metadata = _require_mapping(raw, "metadata")
    spec = _require_mapping(raw, "spec")
    source = _require_mapping(spec, "source")

    name = _require_str(metadata, "name", "metadata")
    base_stage = _require_str(source, "baseStage", "spec.source")

    configuration = spec.get("configuration") or {}
    if not isinstance(configuration, dict):
        raise ManifestError("spec.configuration must be a mapping")

    variant = str(configuration.get("variant", "nominal"))
    variant_set = str(configuration.get("variantSet", "ops"))
    variant_prim = _validate_prim(
        str(configuration.get("variantPrim", "/World/Factory/LineA")),
        "spec.configuration.variantPrim",
    )

    telemetry = spec.get("telemetry") or {}
    if not isinstance(telemetry, dict):
        raise ManifestError("spec.telemetry must be a mapping")

    telemetry_mappings: list[TelemetryMapping] = []
    for index, item in enumerate(telemetry.get("mappings") or []):
        if not isinstance(item, dict):
            raise ManifestError(f"spec.telemetry.mappings[{index}] must be a mapping")
        context = f"spec.telemetry.mappings[{index}]"
        telemetry_mappings.append(
            TelemetryMapping(
                topic=_require_str(item, "topic", context),
                prim=_validate_prim(_require_str(item, "prim", context), context),
                attribute=_require_str(item, "attribute", context),
                default=item.get("default"),
            )
        )

    plm = spec.get("plm") or {}
    if not isinstance(plm, dict):
        raise ManifestError("spec.plm must be a mapping")

    plm_mappings: list[PlmMapping] = []
    for index, item in enumerate(plm.get("mappings") or []):
        if not isinstance(item, dict):
            raise ManifestError(f"spec.plm.mappings[{index}] must be a mapping")
        context = f"spec.plm.mappings[{index}]"
        plm_mappings.append(
            PlmMapping(
                item_id=_require_str(item, "itemId", context),
                prim=_validate_prim(_require_str(item, "prim", context), context),
                revision=str(item.get("revision", "A")),
                lifecycle=str(item.get("lifecycle", "Released")),
            )
        )

    policy = spec.get("policy") or {}
    if not isinstance(policy, dict):
        raise ManifestError("spec.policy must be a mapping")

    thresholds: list[Threshold] = []
    for index, item in enumerate(policy.get("thresholds") or []):
        if not isinstance(item, dict):
            raise ManifestError(f"spec.policy.thresholds[{index}] must be a mapping")
        context = f"spec.policy.thresholds[{index}]"
        thresholds.append(
            Threshold(
                prim=_validate_prim(_require_str(item, "prim", context), context),
                attribute=_require_str(item, "attribute", context),
                warn_above=_as_optional_float(item.get("warnAbove")),
                critical_above=_as_optional_float(item.get("criticalAbove")),
            )
        )

    streaming_raw = spec.get("streaming") or {}
    if not isinstance(streaming_raw, dict):
        raise ManifestError("spec.streaming must be a mapping")
    streaming = StreamingSpec(
        enabled=bool(streaming_raw.get("enabled", False)),
        gpu_class=str(streaming_raw.get("gpuClass", "graphics")),
        idle_timeout=str(streaming_raw.get("idleTimeout", "20m")),
    )

    labels = metadata.get("labels") or {}
    if not isinstance(labels, dict):
        raise ManifestError("metadata.labels must be a mapping")

    manifest = DigitalTwinManifest(
        name=name,
        base_stage=base_stage,
        variant=variant,
        variant_set=variant_set,
        variant_prim=variant_prim,
        telemetry_provider=str(telemetry.get("provider", "mqtt")),
        telemetry_endpoint=str(telemetry.get("endpoint", "")),
        telemetry_mappings=telemetry_mappings,
        plm_provider=str(plm.get("provider", "mock")),
        plm_mappings=plm_mappings,
        thresholds=thresholds,
        streaming=streaming,
        labels={str(k): str(v) for k, v in labels.items()},
        source_path=manifest_path,
    )
    # Fail fast if base stage is missing.
    manifest.resolve_base_stage()
    return manifest


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ManifestError(f"expected numeric threshold, got {value!r}") from exc
