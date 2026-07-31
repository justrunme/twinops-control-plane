"""Generic PLM adapters (mock first; vendor-specific later)."""

from twinops.plm.base import PlmAdapter
from twinops.plm.mock import MockPlmAdapter, PlmItem

__all__ = ["MockPlmAdapter", "PlmAdapter", "PlmItem"]
