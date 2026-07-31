"""Vendor PLM stubs satisfy the protocol surface."""

from __future__ import annotations

import pytest
from twinops.plm.base import PlmAdapter
from twinops.plm.stubs import TeamcenterStubAdapter, WindchillStubAdapter


def test_vendor_stubs_are_plm_adapters() -> None:
    assert isinstance(TeamcenterStubAdapter(), PlmAdapter)
    assert isinstance(WindchillStubAdapter(), PlmAdapter)


def test_vendor_stubs_refuse_mutations() -> None:
    with pytest.raises(NotImplementedError):
        TeamcenterStubAdapter().bump_revision("x")
    with pytest.raises(NotImplementedError):
        WindchillStubAdapter().bump_revision("x")
