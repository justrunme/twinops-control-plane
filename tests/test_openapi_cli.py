"""Tests for twinopsctl openapi."""

from __future__ import annotations

import json
from pathlib import Path

from twinops.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def test_openapi_cli_stdout(capsys, tmp_path: Path) -> None:
    try:
        main(
            [
                "openapi",
                "--example",
                str(EXAMPLE),
                "--work-dir",
                str(tmp_path / "work"),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["info"]["title"] == "TwinOps Live API"
    assert "/api/health" in schema["paths"]


def test_openapi_cli_out(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    try:
        main(
            [
                "openapi",
                "--example",
                str(EXAMPLE),
                "--work-dir",
                str(tmp_path / "work"),
                "--out",
                str(out),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 0
    assert out.is_file()
    assert "TwinOps Live API" in out.read_text(encoding="utf-8")
