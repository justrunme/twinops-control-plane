"""Vendor PLM stubs — shape only, no proprietary SDKs.

These adapters intentionally raise NotImplementedError for mutating calls so
demos stay on MockPlmAdapter until a real integration is chosen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from twinops.plm.mock import PlmItem
from twinops.schema import DigitalTwinManifest


class TeamcenterStubAdapter:
    """Placeholder Teamcenter-shaped adapter (not connected)."""

    provider = "teamcenter-stub"

    @property
    def items(self) -> list[PlmItem]:
        return []

    def get(self, item_id: str) -> PlmItem | None:
        return None

    def bump_revision(self, item_id: str, *, to: str | None = None) -> PlmItem:
        raise NotImplementedError("Teamcenter stub — wire SDK/credentials outside TwinOps core")

    def compare_manifest(self, manifest: DigitalTwinManifest) -> list[dict[str, Any]]:
        raise NotImplementedError("Teamcenter stub — compare not implemented")

    def sync_manifest(self, manifest_path: str | Path, *, write: bool = True) -> dict[str, Any]:
        raise NotImplementedError("Teamcenter stub — sync not implemented")


class WindchillStubAdapter:
    """Placeholder Windchill-shaped adapter (not connected)."""

    provider = "windchill-stub"

    @property
    def items(self) -> list[PlmItem]:
        return []

    def get(self, item_id: str) -> PlmItem | None:
        return None

    def bump_revision(self, item_id: str, *, to: str | None = None) -> PlmItem:
        raise NotImplementedError("Windchill stub — wire SDK/credentials outside TwinOps core")

    def compare_manifest(self, manifest: DigitalTwinManifest) -> list[dict[str, Any]]:
        raise NotImplementedError("Windchill stub — compare not implemented")

    def sync_manifest(self, manifest_path: str | Path, *, write: bool = True) -> dict[str, Any]:
        raise NotImplementedError("Windchill stub — sync not implemented")
