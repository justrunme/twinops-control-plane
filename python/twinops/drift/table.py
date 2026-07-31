"""ASCII table rendering for drift findings."""

from __future__ import annotations

from twinops.drift.engine import DriftReport
from twinops.drift.model import display_value


def render_drift_table(report: DriftReport) -> str:
    headers = ("Prim", "Attribute", "Desired", "Rendered", "Observed", "Status")
    rows: list[tuple[str, str, str, str, str, str]] = []
    for finding in report.findings:
        rows.append(
            (
                finding.short_prim,
                finding.attribute.removeprefix("twinops:"),
                display_value(finding.desired),
                display_value(finding.rendered),
                display_value(finding.observed),
                finding.status,
            )
        )

    if not rows:
        return "No comparable twin attributes found."

    widths = [len(h) for h in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def fmt(cols: tuple[str, ...]) -> str:
        return "│ " + " │ ".join(cell.ljust(widths[i]) for i, cell in enumerate(cols)) + " │"

    def sep(left: str, mid: str, right: str, fill: str = "─") -> str:
        parts = [fill * (width + 2) for width in widths]
        return left + mid.join(parts) + right

    lines = [
        f"TwinOps Drift Report — {report.name}",
        sep("┌", "┬", "┐"),
        fmt(headers),
        sep("├", "┼", "┤"),
    ]
    for row in rows:
        lines.append(fmt(row))
    lines.append(sep("└", "┴", "┘"))

    summary = ", ".join(f"{key}={value}" for key, value in sorted(report.summary.items()))
    if summary:
        lines.append(f"Summary: {summary}")
    if report.has_drift:
        lines.append("Result: DRIFT DETECTED")
    else:
        lines.append("Result: SYNCED")
    return "\n".join(lines)
