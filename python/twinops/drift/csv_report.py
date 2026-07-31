"""CSV export for TwinOps drift findings."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from twinops.drift.engine import DriftReport
from twinops.drift.model import display_value

CSV_HEADERS = (
    "prim",
    "attribute",
    "desired",
    "rendered",
    "observed",
    "status",
    "severity",
    "message",
)


def render_csv_report(report: DriftReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADERS)
    for finding in report.findings:
        writer.writerow(
            [
                finding.prim,
                finding.attribute,
                display_value(finding.desired),
                display_value(finding.rendered),
                display_value(finding.observed),
                finding.status,
                finding.severity,
                finding.message,
            ]
        )
    return buffer.getvalue()


def write_csv_report(report: DriftReport, path: str | Path) -> Path:
    out = Path(path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_csv_report(report), encoding="utf-8")
    return out
