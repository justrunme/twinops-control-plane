"""Tests for offline scene HTML report."""

from __future__ import annotations

from pathlib import Path

from twinops.scene.html_report import render_scene_html, write_scene_html


def test_render_scene_html_contains_lit_prim() -> None:
    scene = {
        "twin": "assembly-line-a",
        "protocol": {"name": "twinops.highlight.v1"},
        "generatedAt": "2026-07-31T00:00:00Z",
        "hasDrift": True,
        "prims": [
            {
                "prim": "/World/Factory/LineA/Robot01",
                "label": "Robot01",
                "status": "CRITICAL",
                "highlight": {"enabled": True, "intensity": 1.0},
            }
        ],
    }
    html = render_scene_html(scene)
    assert "Robot01" in html
    assert "DRIFT HIGHLIGHTS" in html
    assert "twinops.highlight.v1" in html


def test_write_scene_html(tmp_path: Path) -> None:
    path = write_scene_html(
        {
            "twin": "t",
            "protocol": {"name": "twinops.highlight.v1"},
            "hasDrift": False,
            "prims": [],
        },
        tmp_path / "scene.html",
    )
    assert path.is_file()
    assert "ALL CALM" in path.read_text(encoding="utf-8")
