"""Minimal USDA ASCII helpers (no pxr dependency required)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


def escape_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        text = f"{value:.6f}".rstrip("0").rstrip(".")
        return text if text else "0"
    if isinstance(value, str):
        return f'"{escape_string(value)}"'
    raise TypeError(f"unsupported USDA value type: {type(value)!r}")


def infer_usd_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    raise TypeError(f"cannot infer USD type for {value!r}")


@dataclass
class PrimSpec:
    path: str
    attributes: dict[str, Any] = field(default_factory=dict)


def build_overlay_layer(
    *,
    doc: str,
    prims: list[PrimSpec],
    extra_header_lines: list[str] | None = None,
) -> str:
    """Build a sparse overlay USDA from absolute prim paths and attributes."""
    tree: dict[str, dict[str, Any]] = {}
    for prim in prims:
        parts = [part for part in prim.path.split("/") if part]
        if not parts:
            raise ValueError(f"invalid prim path: {prim.path}")
        cursor = tree
        for index, part in enumerate(parts):
            entry = cursor.setdefault(part, {"children": {}, "attrs": {}})
            if index == len(parts) - 1:
                entry["attrs"].update(prim.attributes)
            cursor = entry["children"]

    lines = ["#usda 1.0", "("]
    lines.append(f'    doc = "{escape_string(doc)}"')
    if extra_header_lines:
        for header_line in extra_header_lines:
            lines.append(f"    {header_line}")
    lines.append(")")
    lines.append("")

    def emit(name: str, entry: dict[str, Any], indent: int) -> None:
        pad = " " * indent
        lines.append(f'{pad}over "{name}"')
        lines.append(f"{pad}{{")
        for attr_name, attr_value in sorted(entry["attrs"].items()):
            usd_type = infer_usd_type(attr_value)
            lines.append(
                f"{pad}    custom {usd_type} {attr_name} = {format_value(attr_value)}"
            )
        for child_name, child in sorted(entry["children"].items()):
            emit(child_name, child, indent + 4)
        lines.append(f"{pad}}}")
        lines.append("")

    for root_name, root_entry in sorted(tree.items()):
        emit(root_name, root_entry, 0)

    return "\n".join(lines).rstrip() + "\n"


def build_root_stage(
    *,
    doc: str,
    sublayers: list[str],
    default_prim: str = "World",
) -> str:
    lines = [
        "#usda 1.0",
        "(",
        f'    defaultPrim = "{escape_string(default_prim)}"',
        f'    doc = "{escape_string(doc)}"',
        "    subLayers = [",
    ]
    for layer in sublayers:
        lines.append(f"        @{layer}@")
    lines.extend(
        [
            "    ]",
            ")",
            "",
        ]
    )
    return "\n".join(lines)


def build_variant_overlay(
    *,
    variant_prim: str,
    variant_set: str,
    variant: str,
) -> str:
    parts = [part for part in variant_prim.split("/") if part]
    if not parts:
        raise ValueError(f"invalid variant prim: {variant_prim}")

    lines = [
        "#usda 1.0",
        "(",
        (
            f'    doc = "TwinOps variant selection: '
            f'{escape_string(variant_set)}={escape_string(variant)}"'
        ),
        ")",
        "",
    ]

    for index, part in enumerate(parts):
        pad = " " * (index * 4)
        if index == len(parts) - 1:
            lines.append(f'{pad}over "{part}" (')
            lines.append(f"{pad}    variants = {{")
            lines.append(
                f'{pad}        string {variant_set} = "{escape_string(variant)}"'
            )
            lines.append(f"{pad}    }}")
            lines.append(f"{pad})")
            lines.append(f"{pad}{{")
            lines.append(
                f'{pad}    custom string twinops:selectedVariant = "{escape_string(variant)}"'
            )
            lines.append(f"{pad}}}")
        else:
            lines.append(f'{pad}over "{part}"')
            lines.append(f"{pad}{{")

    for index in range(len(parts) - 2, -1, -1):
        pad = " " * (index * 4)
        lines.append(f"{pad}}}")

    lines.append("")
    return "\n".join(lines)


def discover_variant_names(usda_text: str, variant_set: str) -> set[str]:
    """Best-effort parse of variant names from USDA ASCII."""
    names: set[str] = set()
    marker = f'variantSet "{variant_set}"'
    start = usda_text.find(marker)
    if start < 0:
        return names

    # Walk from the opening brace of the variantSet with brace depth tracking.
    brace_at = usda_text.find("{", start)
    if brace_at < 0:
        return names

    depth = 0
    i = brace_at
    body_start = brace_at + 1
    while i < len(usda_text):
        char = usda_text[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                body = usda_text[body_start:i]
                break
        i += 1
    else:
        return names

    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith('"') and "{" in stripped:
            end_quote = stripped.index('"', 1)
            names.add(stripped[1:end_quote])
    return names


def group_attributes_by_prim(items: list[tuple[str, str, Any]]) -> list[PrimSpec]:
    grouped: dict[str, dict[str, Any]] = defaultdict(dict)
    for prim, attribute, value in items:
        grouped[prim][attribute] = value
    return [PrimSpec(path=prim, attributes=attrs) for prim, attrs in sorted(grouped.items())]
