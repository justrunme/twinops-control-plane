"""Self-contained HTML scene highlight report (offline / Git-friendly)."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

_STATUS_COLOR = {
    "SYNCED": "#1f9d55",
    "WARNING": "#d97706",
    "MISSING": "#6b7280",
    "DRIFT": "#dc2626",
    "CRITICAL": "#991b1b",
}


def write_scene_html(scene: dict[str, Any], path: str | Path) -> Path:
    out = Path(path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_scene_html(scene), encoding="utf-8")
    return out


def render_scene_html(scene: dict[str, Any]) -> str:
    twin = html.escape(str(scene.get("twin") or "twin"))
    protocol = html.escape(str((scene.get("protocol") or {}).get("name") or "twinops.highlight.v1"))
    generated = html.escape(str(scene.get("generatedAt") or ""))
    has_drift = bool(scene.get("hasDrift"))
    result = "DRIFT HIGHLIGHTS" if has_drift else "ALL CALM"
    result_color = "#dc2626" if has_drift else "#1f9d55"

    cards = []
    for prim in scene.get("prims") or []:
        status = str(prim.get("status") or "SYNCED")
        color = _STATUS_COLOR.get(status, "#334155")
        lit = bool((prim.get("highlight") or {}).get("enabled"))
        intensity = (prim.get("highlight") or {}).get("intensity", 0)
        label = html.escape(str(prim.get("label") or prim.get("prim") or ""))
        path = html.escape(str(prim.get("prim") or ""))
        glow = f"box-shadow: 0 0 {10 + float(intensity) * 18:.0f}px {color}66;" if lit else ""
        cards.append(
            f"<article class='card {'lit' if lit else ''}' style='border-color:{color};{glow}'>"
            f"<div class='dot' style='background:{color}'></div>"
            f"<div><strong>{label}</strong><code>{path}</code></div>"
            f"<span class='pill' style='background:{color}'>{html.escape(status)}</span>"
            "</article>"
        )

    body = "\n".join(cards) if cards else "<p class='empty'>No prims in snapshot.</p>"
    raw = html.escape(json.dumps(scene, indent=2))

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>TwinOps Scene — {twin}</title>
  <style>
    :root {{
      --bg: #0b1220;
      --panel: #111827;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --line: #1f2937;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(900px 480px at 0% 0%, #134e4a 0%, transparent 50%),
        radial-gradient(800px 420px at 100% 10%, #1e3a5f 0%, transparent 45%),
        var(--bg);
      min-height: 100vh;
      padding: 32px;
    }}
    .wrap {{ max-width: 960px; margin: 0 auto; }}
    header {{
      display: flex; justify-content: space-between; gap: 16px; align-items: end;
      margin-bottom: 24px; flex-wrap: wrap;
    }}
    h1 {{ margin: 0; font-size: 1.6rem; letter-spacing: -0.02em; }}
    .meta {{ color: var(--muted); font-size: 0.9rem; }}
    .badge {{
      display: inline-block; padding: 8px 14px; border-radius: 999px;
      background: {result_color}; color: white; font-weight: 600; font-size: 0.85rem;
    }}
    .grid {{ display: grid; gap: 12px; }}
    .card {{
      display: grid; grid-template-columns: 14px 1fr auto; gap: 12px; align-items: center;
      background: color-mix(in srgb, var(--panel) 92%, transparent);
      border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px;
    }}
    .card strong {{ display: block; }}
    .card code {{ color: var(--muted); font-size: 0.8rem; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
    .pill {{
      font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em;
      padding: 4px 8px; border-radius: 999px; color: white;
    }}
    details {{
      margin-top: 28px; background: var(--panel); border: 1px solid var(--line);
      border-radius: 14px; padding: 12px 16px;
    }}
    pre {{
      overflow: auto; color: #cbd5e1; font-size: 0.78rem; line-height: 1.45;
    }}
    .empty {{ color: var(--muted); }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>Scene highlights — {twin}</h1>
        <div class="meta">{protocol} · {generated}</div>
      </div>
      <span class="badge">{result}</span>
    </header>
    <div class="grid">
      {body}
    </div>
    <details>
      <summary>Raw twinops.highlight.v1 JSON</summary>
      <pre>{raw}</pre>
    </details>
  </div>
</body>
</html>
"""
