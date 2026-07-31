"""Vendor-neutral PLM adapter protocol.

FilePlmAdapter and RestPlmAdapter implement this for demos. Vendor stubs
(Teamcenter/Windchill) show the shape only — no proprietary SDKs in-tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from twinops.plm.mock import PlmItem
from twinops.schema import DigitalTwinManifest


@runtime_checkable
class PlmAdapter(Protocol):
    """Minimal PLM operations TwinOps relies on."""

    @property
    def items(self) -> list[PlmItem]: ...

    def get(self, item_id: str) -> PlmItem | None: ...

    def bump_revision(self, item_id: str, *, to: str | None = None) -> PlmItem: ...

    def compare_manifest(self, manifest: DigitalTwinManifest) -> list[dict[str, Any]]: ...

    def sync_manifest(self, manifest_path: str | Path, *, write: bool = True) -> dict[str, Any]: ...
