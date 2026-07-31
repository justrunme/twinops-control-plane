"""Mock PLM adapter for TwinOps demos.

Reads a JSON catalog (itemId → revision/lifecycle/prim) and can:
- sync catalog values into a DigitalTwin manifest
- bump a revision (simulating an engineering change)
- emit a desired-state fragment for drift demos

This is intentionally vendor-neutral — not Teamcenter/Windchill/etc.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from twinops.schema import DigitalTwinManifest, load_manifest


@dataclass(frozen=True)
class PlmItem:
    item_id: str
    revision: str
    lifecycle: str
    prim: str
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MockPlmAdapter:
    def __init__(self, items: list[PlmItem]) -> None:
        self._items = {item.item_id: item for item in items}

    @classmethod
    def from_catalog(cls, path: str | Path) -> MockPlmAdapter:
        catalog_path = Path(path)
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("PLM catalog root must be an object")
        raw_items = data.get("items") or []
        if not isinstance(raw_items, list):
            raise ValueError("PLM catalog.items must be a list")
        items: list[PlmItem] = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                raise ValueError(f"catalog.items[{index}] must be an object")
            items.append(
                PlmItem(
                    item_id=str(item["itemId"]),
                    revision=str(item.get("revision", "A")),
                    lifecycle=str(item.get("lifecycle", "Released")),
                    prim=str(item["prim"]),
                    name=str(item.get("name", "")),
                )
            )
        return cls(items)

    @property
    def items(self) -> list[PlmItem]:
        return sorted(self._items.values(), key=lambda item: item.item_id)

    def get(self, item_id: str) -> PlmItem | None:
        return self._items.get(item_id)

    def bump_revision(self, item_id: str, *, to: str | None = None) -> PlmItem:
        current = self._items.get(item_id)
        if current is None:
            raise KeyError(f"unknown PLM item: {item_id}")
        if to is None:
            # Simple alphabetic bump: A→B→C… or append +.
            rev = current.revision
            if len(rev) == 1 and rev.isalpha():
                to = chr(ord(rev.upper()) + 1)
            else:
                to = f"{rev}+"
        updated = PlmItem(
            item_id=current.item_id,
            revision=to,
            lifecycle=current.lifecycle,
            prim=current.prim,
            name=current.name,
        )
        self._items[item_id] = updated
        return updated

    def write_catalog(self, path: str | Path, *, provider: str = "mock") -> Path:
        target = Path(path)
        payload = {
            "provider": provider,
            "items": [
                {
                    "itemId": item.item_id,
                    "revision": item.revision,
                    "lifecycle": item.lifecycle,
                    "prim": item.prim,
                    **({"name": item.name} if item.name else {}),
                }
                for item in self.items
            ],
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return target

    def sync_manifest(self, manifest_path: str | Path, *, write: bool = True) -> dict[str, Any]:
        """Overwrite manifest PLM mappings from catalog; return a sync report."""
        path = Path(manifest_path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("manifest root must be a mapping")
        spec = raw.setdefault("spec", {})
        if not isinstance(spec, dict):
            raise ValueError("manifest.spec must be a mapping")
        plm = spec.setdefault("plm", {})
        if not isinstance(plm, dict):
            raise ValueError("manifest.spec.plm must be a mapping")
        plm["provider"] = plm.get("provider") or "mock"
        before = {
            str(item.get("itemId")): str(item.get("revision"))
            for item in (plm.get("mappings") or [])
            if isinstance(item, dict)
        }
        mappings = [
            {
                "itemId": item.item_id,
                "revision": item.revision,
                "lifecycle": item.lifecycle,
                "prim": item.prim,
            }
            for item in self.items
        ]
        plm["mappings"] = mappings
        after = {item["itemId"]: item["revision"] for item in mappings}
        changed = [
            {"itemId": item_id, "from": before.get(item_id), "to": revision}
            for item_id, revision in after.items()
            if before.get(item_id) != revision
        ]
        if write:
            path.write_text(
                yaml.safe_dump(raw, sort_keys=False, allow_unicode=False),
                encoding="utf-8",
            )
        return {
            "manifest": str(path),
            "provider": plm["provider"],
            "items": len(mappings),
            "changed": changed,
        }

    def desired_fragment(self) -> dict[str, Any]:
        """Desired-state resources covering PLM attributes only."""
        return {
            "apiVersion": "twinops.io/v1alpha1",
            "kind": "DesiredState",
            "metadata": {"name": "plm-desired"},
            "spec": {
                "resources": [
                    {
                        "prim": item.prim,
                        "attributes": {
                            "twinops:plmItemId": item.item_id,
                            "twinops:plmRevision": item.revision,
                            "twinops:lifecycle": item.lifecycle,
                        },
                    }
                    for item in self.items
                ]
            },
        }

    def compare_manifest(self, manifest: DigitalTwinManifest) -> list[dict[str, Any]]:
        diffs: list[dict[str, Any]] = []
        by_id = {mapping.item_id: mapping for mapping in manifest.plm_mappings}
        for item in self.items:
            current = by_id.get(item.item_id)
            if current is None:
                diffs.append(
                    {
                        "itemId": item.item_id,
                        "status": "MISSING_IN_MANIFEST",
                        "catalogRevision": item.revision,
                    }
                )
                continue
            if current.revision != item.revision or current.lifecycle != item.lifecycle:
                diffs.append(
                    {
                        "itemId": item.item_id,
                        "status": "DRIFT",
                        "manifestRevision": current.revision,
                        "catalogRevision": item.revision,
                        "manifestLifecycle": current.lifecycle,
                        "catalogLifecycle": item.lifecycle,
                        "prim": item.prim,
                    }
                )
            else:
                diffs.append(
                    {
                        "itemId": item.item_id,
                        "status": "SYNCED",
                        "revision": item.revision,
                        "prim": item.prim,
                    }
                )
        return diffs


def load_adapter_for_example(example_dir: str | Path) -> tuple[MockPlmAdapter, Path]:
    root = Path(example_dir)
    catalog = root / "plm-catalog.json"
    if not catalog.is_file():
        raise FileNotFoundError(f"PLM catalog not found: {catalog}")
    return MockPlmAdapter.from_catalog(catalog), catalog


def ensure_catalog_from_manifest(manifest_path: str | Path, catalog_path: str | Path) -> Path:
    """Bootstrap a catalog file from an existing DigitalTwin manifest."""
    manifest = load_manifest(manifest_path)
    adapter = MockPlmAdapter(
        [
            PlmItem(
                item_id=mapping.item_id,
                revision=mapping.revision,
                lifecycle=mapping.lifecycle,
                prim=mapping.prim,
            )
            for mapping in manifest.plm_mappings
        ]
    )
    return adapter.write_catalog(catalog_path, provider=manifest.plm_provider)
