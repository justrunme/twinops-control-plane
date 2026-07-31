"""Load desired / observed / rendered twin state."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from twinops.drift.model import DesiredResource, DesiredState, ObservedState, normalize_attr
from twinops.schema.manifest import ManifestError

_ATTR_RE = re.compile(
    r"^\s*custom\s+(?:string|float|double|int|bool)\s+(?P<name>[\w:]+)\s*=\s*(?P<value>.+?)\s*$"
)
_PRIM_RE = re.compile(r'^\s*(?:over|def\s+\w+)\s+"(?P<name>[^"]+)"')
_SUBLAYER_RE = re.compile(r"@([^@]+)@")


class DriftLoadError(ValueError):
    """Raised when drift inputs cannot be loaded."""


def load_desired_state(path: str | Path) -> DesiredState:
    desired_path = Path(path).resolve()
    if not desired_path.is_file():
        raise DriftLoadError(f"desired state not found: {desired_path}")

    with desired_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise DriftLoadError("desired state root must be a mapping")

    kind = raw.get("kind")
    if kind not in {"TwinDesiredState", "DigitalTwin"}:
        raise DriftLoadError(
            f"unsupported desired kind '{kind}', expected TwinDesiredState"
        )

    metadata = raw.get("metadata") or {}
    name = str(metadata.get("name") or desired_path.stem)
    spec = raw.get("spec") or {}

    resources: list[DesiredResource] = []
    if kind == "TwinDesiredState":
        for index, item in enumerate(spec.get("resources") or []):
            if not isinstance(item, dict):
                raise DriftLoadError(f"spec.resources[{index}] must be a mapping")
            prim = item.get("prim")
            if not isinstance(prim, str) or not prim.startswith("/"):
                raise DriftLoadError(f"spec.resources[{index}].prim is invalid")
            attrs = {
                normalize_attr(key): value
                for key, value in item.items()
                if key != "prim"
            }
            resources.append(DesiredResource(prim=prim, attributes=attrs))
    else:
        from twinops.schema.manifest import load_manifest

        try:
            manifest = load_manifest(desired_path)
        except ManifestError as exc:
            raise DriftLoadError(str(exc)) from exc
        by_prim: dict[str, dict[str, Any]] = {}
        for mapping in manifest.plm_mappings:
            by_prim.setdefault(mapping.prim, {})
            by_prim[mapping.prim]["twinops:plmItemId"] = mapping.item_id
            by_prim[mapping.prim]["twinops:plmRevision"] = mapping.revision
            by_prim[mapping.prim]["twinops:lifecycle"] = mapping.lifecycle
        for mapping in manifest.telemetry_mappings:
            attr = mapping.attribute
            if not attr.startswith("twinops:"):
                attr = f"twinops:{attr}"
            if mapping.default is not None:
                by_prim.setdefault(mapping.prim, {})
                by_prim[mapping.prim][attr] = mapping.default
        resources = [
            DesiredResource(prim=prim, attributes=attrs)
            for prim, attrs in sorted(by_prim.items())
        ]
        name = manifest.name

    return DesiredState(name=name, resources=resources)


def load_observed_state(path: str | Path) -> ObservedState:
    observed_path = Path(path).resolve()
    if not observed_path.is_file():
        raise DriftLoadError(f"observed telemetry not found: {observed_path}")

    with observed_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise DriftLoadError("observed telemetry root must be an object")

    attrs_by_prim: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw.get("observations") or []):
        if not isinstance(item, dict):
            raise DriftLoadError(f"observations[{index}] must be an object")
        prim = item.get("prim")
        if not isinstance(prim, str):
            raise DriftLoadError(f"observations[{index}].prim must be a string")
        attributes = item.get("attributes") or {}
        if not isinstance(attributes, dict):
            raise DriftLoadError(f"observations[{index}].attributes must be an object")
        normalized = {normalize_attr(str(k)): v for k, v in attributes.items()}
        attrs_by_prim.setdefault(prim, {}).update(normalized)

    return ObservedState(
        timestamp=raw.get("timestamp"),
        source=raw.get("source"),
        attributes_by_prim=attrs_by_prim,
    )


def extract_rendered_attributes(stage_path: str | Path) -> dict[str, dict[str, Any]]:
    """Resolve twinops:* attributes from a composed USDA root stage."""
    root = Path(stage_path).resolve()
    if not root.is_file():
        raise DriftLoadError(f"stage not found: {root}")

    root_text = root.read_text(encoding="utf-8")
    layer_paths = _resolve_sublayers(root, root_text)
    resolved: dict[str, dict[str, Any]] = {}
    # Strongest to weakest: first sublayer wins in OpenUSD.
    for layer_path in layer_paths:
        layer_attrs = _parse_usda_attributes(layer_path)
        for prim, attrs in layer_attrs.items():
            bucket = resolved.setdefault(prim, {})
            for key, value in attrs.items():
                if key not in bucket:
                    bucket[key] = value
    for prim, attrs in _parse_usda_text(root_text).items():
        bucket = resolved.setdefault(prim, {})
        for key, value in attrs.items():
            if key not in bucket:
                bucket[key] = value
    return resolved


def _resolve_sublayers(root: Path, root_text: str) -> list[Path]:
    paths: list[Path] = []
    for match in _SUBLAYER_RE.finditer(root_text):
        ref = match.group(1)
        if ref.startswith("file:"):
            candidate = Path(ref.removeprefix("file://"))
        else:
            candidate = (root.parent / ref).resolve()
        if candidate.is_file():
            paths.append(candidate)
    return paths


def _parse_usda_attributes(path: Path) -> dict[str, dict[str, Any]]:
    return _parse_usda_text(path.read_text(encoding="utf-8"))


def _parse_usda_text(text: str) -> dict[str, dict[str, Any]]:
    """Parse custom twinops attributes with brace-aware prim scoping."""
    stack: list[tuple[str, int]] = []
    result: dict[str, dict[str, Any]] = {}
    depth = 0
    pending_prim: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0]
        if not line.strip():
            continue

        prim_match = _PRIM_RE.match(line)
        if prim_match:
            pending_prim = prim_match.group("name")

        # Count braces after handling prim open.
        opens = line.count("{")
        closes = line.count("}")

        if pending_prim is not None and opens > 0:
            # Prim scope opens at the first '{' on/after the prim declaration.
            stack.append((pending_prim, depth + 1))
            pending_prim = None

        depth += opens

        attr = _ATTR_RE.match(line)
        if attr and stack:
            name = attr.group("name")
            if name.startswith("twinops:"):
                prim = "/" + "/".join(item[0] for item in stack)
                result.setdefault(prim, {})[name] = _parse_usda_value(attr.group("value"))

        for _ in range(closes):
            depth -= 1
            while stack and stack[-1][1] > depth:
                stack.pop()
            if pending_prim is not None and opens == 0:
                # Declaration-only line without body yet.
                pass

    return result


def _parse_usda_value(raw: str) -> Any:
    text = raw.strip()
    if text in {"true", "false"}:
        return text == "true"
    if text.startswith('"') and text.endswith('"'):
        inner = text[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    try:
        if any(marker in text for marker in (".", "e", "E")):
            return float(text)
        return int(text)
    except ValueError:
        return text
