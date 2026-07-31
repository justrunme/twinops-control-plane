"""Ensure mock PLM satisfies the vendor-neutral protocol."""

from __future__ import annotations

from pathlib import Path

from twinops.plm.base import PlmAdapter
from twinops.plm.mock import MockPlmAdapter

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "examples" / "assembly-line" / "plm-catalog.json"


def test_mock_adapter_is_plm_adapter() -> None:
    adapter = MockPlmAdapter.from_catalog(CATALOG)
    assert isinstance(adapter, PlmAdapter)
    assert adapter.items
