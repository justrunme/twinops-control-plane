"""Generic PLM adapters (file + REST; vendor stubs for later)."""

from twinops.plm.base import PlmAdapter
from twinops.plm.file import FilePlmAdapter
from twinops.plm.mock import MockPlmAdapter, PlmItem
from twinops.plm.rest import RestPlmAdapter
from twinops.plm.stubs import TeamcenterStubAdapter, WindchillStubAdapter

__all__ = [
    "FilePlmAdapter",
    "MockPlmAdapter",
    "PlmAdapter",
    "PlmItem",
    "RestPlmAdapter",
    "TeamcenterStubAdapter",
    "WindchillStubAdapter",
]
