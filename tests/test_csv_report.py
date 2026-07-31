"""Tests for drift CSV export."""

from __future__ import annotations

from pathlib import Path

from twinops.drift.csv_report import render_csv_report, write_csv_report
from twinops.drift.engine import DriftReport
from twinops.drift.model import DriftFinding


def test_render_csv_report() -> None:
    report = DriftReport(
        name="assembly-line-a",
        findings=[
            DriftFinding(
                prim="/World/Robot01",
                attribute="twinops:temperature",
                desired=40,
                rendered=40,
                observed=95,
                status="CRITICAL",
                severity="critical",
                message="hot",
            )
        ],
    )
    text = render_csv_report(report)
    assert "prim,attribute,desired" in text
    assert "CRITICAL" in text
    assert "Robot01" in text


def test_write_csv_report(tmp_path: Path) -> None:
    path = write_csv_report(DriftReport(name="t"), tmp_path / "out.csv")
    assert path.read_text(encoding="utf-8").startswith("prim,")
