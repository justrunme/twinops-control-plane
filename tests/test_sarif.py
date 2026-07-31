"""Tests for SARIF drift export."""

from __future__ import annotations

import json
from pathlib import Path

from twinops.drift.engine import DriftReport
from twinops.drift.model import DriftFinding
from twinops.drift.sarif import report_to_sarif, write_sarif_report


def _sample_report() -> DriftReport:
    return DriftReport(
        name="assembly-line-a",
        generated_at="2026-07-31T00:00:00Z",
        findings=[
            DriftFinding(
                prim="/World/Robot01",
                attribute="twinops:temperature",
                desired=40,
                rendered=40,
                observed=95,
                status="CRITICAL",
                severity="critical",
                message="temperature above critical threshold",
            ),
            DriftFinding(
                prim="/World/Robot01",
                attribute="twinops:status",
                desired="running",
                rendered="running",
                observed="running",
                status="SYNCED",
                severity="info",
                message="ok",
            ),
        ],
        summary={"CRITICAL": 1, "SYNCED": 1},
    )


def test_report_to_sarif_skips_synced() -> None:
    sarif = report_to_sarif(_sample_report())
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "twinopsctl"
    assert len(run["results"]) == 1
    result = run["results"][0]
    assert result["ruleId"] == "twinops-drift/critical"
    assert result["level"] == "error"
    assert "temperature" in result["message"]["text"]


def test_write_sarif_report(tmp_path: Path) -> None:
    path = write_sarif_report(_sample_report(), tmp_path / "drift.sarif")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["runs"][0]["properties"]["hasDrift"] is True
