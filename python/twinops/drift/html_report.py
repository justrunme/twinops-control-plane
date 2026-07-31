"""Generate a self-contained HTML drift dashboard."""

from __future__ import annotations

import html
from pathlib import Path

from twinops.drift.engine import DriftReport
from twinops.drift.model import display_value

_STATUS_COLOR = {
    "SYNCED": "#1f9d55",
    "WARNING": "#d97706",
    "MISSING": "#6b7280",
    "DRIFT": "#dc2626",
    "CRITICAL": "#991b1b",
}


def write_html_report(report: DriftReport, path: str | Path) -> Path:
    out = Path(path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html_report(report), encoding="utf-8")
    return out


def render_html_report(report: DriftReport) -> str:
    rows = []
    for finding in report.findings:
        color = _STATUS_COLOR.get(finding.status, "#334155")
        rows.append(
            "<tr>"
            f"<td>{html.escape(finding.short_prim)}</td>"
            f"<td><code>{html.escape(finding.attribute)}</code></td>"
            f"<td>{html.escape(display_value(finding.desired))}</td>"
            f"<td>{html.escape(display_value(finding.rendered))}</td>"
            f"<td>{html.escape(display_value(finding.observed))}</td>"
            f"<td><span class='pill' style='background:{color}'>"
            f"{html.escape(finding.status)}</span></td>"
            f"<td>{html.escape(finding.message)}</td>"
            "</tr>"
        )

    summary_bits = "".join(
        f"<div class='stat'><strong>{html.escape(k)}</strong><span>{v}</span></div>"
        for k, v in sorted(report.summary.items())
    )
    result = "DRIFT DETECTED" if report.has_drift else "SYNCED"
    result_color = "#dc2626" if report.has_drift else "#1f9d55"

    body_rows = "\n".join(rows) if rows else "<tr><td colspan='7'>No findings</td></tr>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>TwinOps Drift — {html.escape(report.name)}</title>
  <style>
    :root {{
      --bg: #0f172a;
      --panel: #111827;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --line: #1f2937;
      --accent: #38bdf8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(1200px 600px at 10% -10%, #164e63 0%, transparent 50%),
        radial-gradient(900px 500px at 100% 0%, #312e81 0%, transparent 45%),
        var(--bg);
      min-height: 100vh;
      padding: 32px;
    }}
    .wrap {{ max-width: 1100px; margin: 0 auto; }}
    h1 {{
      font-family: "IBM Plex Mono", "SF Mono", monospace;
      font-size: 1.6rem;
      margin: 0 0 8px;
      letter-spacing: 0.02em;
    }}
    .sub {{ color: var(--muted); margin-bottom: 24px; }}
    .banner {{
      display: inline-block;
      padding: 8px 14px;
      border-radius: 999px;
      background: {result_color};
      color: white;
      font-weight: 700;
      margin-bottom: 20px;
    }}
    .stats {{
      display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px;
    }}
    .stat {{
      background: rgba(17, 24, 39, 0.85);
      border: 1px solid var(--line);
      padding: 12px 16px;
      border-radius: 12px;
      min-width: 110px;
    }}
    .stat strong {{ display: block; color: var(--accent); font-size: 0.8rem; }}
    .stat span {{ font-size: 1.4rem; font-weight: 700; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: rgba(17, 24, 39, 0.9);
      border: 1px solid var(--line);
      border-radius: 16px;
      overflow: hidden;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 0.92rem;
    }}
    th {{
      color: var(--muted);
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      background: #0b1220;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{ color: #7dd3fc; }}
    .pill {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      color: white;
      font-size: 0.75rem;
      font-weight: 700;
    }}
    .legend {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 0.85rem;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>TwinOps Drift</h1>
    <div class="sub">{html.escape(report.name)} · {html.escape(report.generated_at or "n/a")}</div>
    <div class="banner">{result}</div>
    <div class="stats">{summary_bits}</div>
    <table>
      <thead>
        <tr>
          <th>Prim</th><th>Attribute</th><th>Desired</th>
          <th>Rendered</th><th>Observed</th><th>Status</th><th>Message</th>
        </tr>
      </thead>
      <tbody>
        {body_rows}
      </tbody>
    </table>
    <div class="legend">
      Green = synced · Yellow = warning · Red = drift/critical · Gray = telemetry missing
    </div>
  </div>
</body>
</html>
"""
