"""Tests for twinopsctl apply / local GitOps apply."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from twinops.cli import main
from twinops.drift.apply import apply_proposal
from twinops.drift.engine import detect_drift
from twinops.drift.reconcile import propose_reconciliation

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


def test_apply_proposal_commits_on_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README").write_text("demo\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "init")

    report = detect_drift(
        desired=EXAMPLE / "desired.yaml",
        stage=EXAMPLE / "generated" / "root.usda",
        observed=EXAMPLE / "telemetry.json",
        manifest=EXAMPLE / "twin.yaml",
    )
    # Force at least a proposal directory with artifacts.
    proposal = propose_reconciliation(report, tmp_path / "proposal")
    result = apply_proposal(
        proposal.output_dir,
        repo=repo,
        target_dir=repo / "usd" / "generated" / "applied",
        commit=True,
    )
    assert result.branch == "reconcile/twinops-auto"
    assert (repo / "usd" / "generated" / "applied" / "reconcile-overlay.usda").is_file()
    assert (repo / "usd" / "generated" / "applied" / "apply-receipt.json").is_file()
    assert result.committed is True
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert branch.stdout.strip() == "reconcile/twinops-auto"


def test_apply_cli_json(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README").write_text("demo\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "init")

    report = detect_drift(
        desired=EXAMPLE / "desired.yaml",
        stage=EXAMPLE / "generated" / "root.usda",
        observed=EXAMPLE / "telemetry.json",
        manifest=EXAMPLE / "twin.yaml",
    )
    proposal = propose_reconciliation(report, tmp_path / "proposal")
    try:
        main(
            [
                "apply",
                str(proposal.output_dir),
                "--repo",
                str(repo),
                "--no-commit",
                "--json",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "ReconciliationApply"
    assert payload["status"]["committed"] is False
