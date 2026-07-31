"""Tests for twinopsctl apply / local GitOps apply."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from twinops.cli import main
from twinops.drift.apply import apply_proposal, render_pr_create_hint


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
        '#usda 1.0\n(\n    doc = "test overlay"\n)\n',
        encoding="utf-8",
    )
    (path / "reconciliation-proposal.json").write_text(
        json.dumps(
            {
                "apiVersion": "twinops.io/v1alpha1",
                "kind": "ReconciliationProposal",
                "status": {
                    "recommendedBranch": "reconcile/twinops-auto",
                    "recommendedAction": "open-pull-request",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "PULL_REQUEST.md").write_text("# test\n", encoding="utf-8")
    return path


def test_apply_proposal_commits_on_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README").write_text("demo\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "init")

    proposal = _write_proposal(tmp_path / "proposal")
    result = apply_proposal(
        proposal,
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

    proposal = _write_proposal(tmp_path / "proposal")
    try:
        main(
            [
                "apply",
                str(proposal),
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


def test_render_pr_create_hint(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README").write_text("demo\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "init")
    proposal = _write_proposal(tmp_path / "proposal")
    (proposal / "PULL_REQUEST.md").write_text("# Fix robot drift\n\nbody\n", encoding="utf-8")
    result = apply_proposal(proposal, repo=repo, commit=False)
    hint = render_pr_create_hint(result)
    assert "gh pr create" in hint
    assert "Fix robot drift" in hint
    assert result.branch in hint
