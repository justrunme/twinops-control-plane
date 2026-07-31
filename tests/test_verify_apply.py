"""Tests for apply → compose → re-drift verification."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from twinops.cli import main
from twinops.drift.verify import verify_apply

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assembly-line"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_proposal(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "reconcile-overlay.usda").write_text(
        '#usda 1.0\n(\n    doc = "verify overlay"\n)\n',
        encoding="utf-8",
    )
    (path / "reconciliation-proposal.json").write_text(
        json.dumps(
            {
                "status": {"recommendedBranch": "reconcile/twinops-auto"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "PULL_REQUEST.md").write_text("# verify\n", encoding="utf-8")
    return path


def test_verify_apply_runs(tmp_path: Path) -> None:
    proposal = _write_proposal(tmp_path / "proposal")
    result = verify_apply(
        manifest=EXAMPLE / "twin.yaml",
        desired=EXAMPLE / "desired.yaml",
        observed=EXAMPLE / "telemetry.json",
        overlay=proposal / "reconcile-overlay.usda",
        stage_out=tmp_path / "stage",
    )
    assert result.stage_root.is_file()
    assert (tmp_path / "stage" / "reconcile-overlay.usda").is_file()
    assert "hasDrift" in result.to_dict()["status"]


def test_apply_verify_cli(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README").write_text("demo\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "init")
    proposal = _write_proposal(tmp_path / "proposal")
    try:
        main(
            [
                "apply",
                str(proposal),
                "--repo",
                str(repo),
                "--no-commit",
                "--verify",
                "--manifest",
                str(EXAMPLE / "twin.yaml"),
                "--desired",
                str(EXAMPLE / "desired.yaml"),
                "--observed",
                str(EXAMPLE / "telemetry.json"),
                "--stage-out",
                str(tmp_path / "verify-stage"),
                "--json",
            ]
        )
    except SystemExit as exc:
        # Exit 1 is OK when sample telemetry still has drift after empty overlay.
        assert exc.code in (0, 1)
    payload = json.loads(capsys.readouterr().out)
    assert "verify" in payload["status"]
    assert payload["status"]["verify"]["kind"] == "ReconciliationVerify"
