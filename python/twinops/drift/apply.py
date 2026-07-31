"""Apply a reconciliation proposal into a local GitOps working tree.

Demo-safe: creates/checks out a recommended branch, copies proposal artifacts,
optionally stages + commits. Never pushes to a remote.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class ApplyResult:
    proposal_dir: Path
    target_dir: Path
    branch: str
    committed: bool
    commit_sha: str | None
    files: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": "twinops.io/v1alpha1",
            "kind": "ReconciliationApply",
            "metadata": {
                "appliedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
            "spec": {
                "proposalDir": str(self.proposal_dir),
                "targetDir": str(self.target_dir),
                "branch": self.branch,
            },
            "status": {
                "committed": self.committed,
                "commitSha": self.commit_sha,
                "files": self.files,
                "notes": [
                    "Local apply only — no remote push",
                    "Review overlay, then re-run twinopsctl build + drift",
                ],
            },
        }


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def _is_git_repo(path: Path) -> bool:
    return _run_git(path, "rev-parse", "--is-inside-work-tree").returncode == 0


def _load_branch(proposal_dir: Path, override: str | None) -> str:
    if override:
        return override
    proposal_path = proposal_dir / "reconciliation-proposal.json"
    if proposal_path.is_file():
        try:
            data = json.loads(proposal_path.read_text(encoding="utf-8"))
            branch = (data.get("status") or {}).get("recommendedBranch")
            if isinstance(branch, str) and branch.strip():
                return branch.strip()
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return "reconcile/twinops-auto"


def apply_proposal(
    proposal_dir: str | Path,
    *,
    repo: str | Path | None = None,
    target_dir: str | Path | None = None,
    branch: str | None = None,
    commit: bool = True,
) -> ApplyResult:
    """Copy proposal artifacts into the repo and optionally commit on a branch."""
    source = Path(proposal_dir).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"proposal directory not found: {source}")

    overlay = source / "reconcile-overlay.usda"
    proposal_json = source / "reconciliation-proposal.json"
    pr_md = source / "PULL_REQUEST.md"
    missing = [p.name for p in (overlay, proposal_json) if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            f"proposal artifacts missing in {source}: {', '.join(missing)}"
        )

    repo_root = Path(repo).resolve() if repo else Path.cwd().resolve()
    dest = (
        Path(target_dir).resolve()
        if target_dir
        else (repo_root / "usd" / "generated" / "applied")
    )
    dest.mkdir(parents=True, exist_ok=True)

    branch_name = _load_branch(source, branch)
    committed = False
    commit_sha: str | None = None
    files: list[str] = []

    if _is_git_repo(repo_root):
        # Create or switch branch without failing if it already exists.
        current = _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
        if current.stdout.strip() != branch_name:
            created = _run_git(repo_root, "checkout", "-b", branch_name)
            if created.returncode != 0:
                switched = _run_git(repo_root, "checkout", branch_name)
                if switched.returncode != 0:
                    raise RuntimeError(
                        f"cannot checkout branch {branch_name!r}: "
                        f"{switched.stderr.strip() or created.stderr.strip()}"
                    )

    for src in (overlay, proposal_json, pr_md):
        if not src.is_file():
            continue
        out = dest / src.name
        shutil.copy2(src, out)
        files.append(str(out.relative_to(repo_root)) if out.is_relative_to(repo_root) else str(out))

    apply_receipt = dest / "apply-receipt.json"
    receipt = {
        "apiVersion": "twinops.io/v1alpha1",
        "kind": "ReconciliationApplyReceipt",
        "metadata": {
            "appliedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "branch": branch_name,
        },
        "spec": {
            "proposalDir": str(source),
            "files": [Path(f).name for f in files],
        },
    }
    apply_receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    receipt_rel = (
        str(apply_receipt.relative_to(repo_root))
        if apply_receipt.is_relative_to(repo_root)
        else str(apply_receipt)
    )
    files.append(receipt_rel)

    if commit and _is_git_repo(repo_root):
        rel_paths = []
        for path in files:
            candidate = repo_root / path if not Path(path).is_absolute() else Path(path)
            if candidate.is_file() and candidate.is_relative_to(repo_root):
                rel_paths.append(str(candidate.relative_to(repo_root)))
        if rel_paths:
            add = _run_git(repo_root, "add", "--", *rel_paths)
            if add.returncode != 0:
                raise RuntimeError(f"git add failed: {add.stderr.strip()}")
            msg = (
                "Apply TwinOps reconciliation proposal\n\n"
                "Local GitOps apply from twinopsctl; review before push/PR."
            )
            committed_proc = _run_git(
                repo_root,
                "-c",
                "user.name=TwinOps",
                "-c",
                "user.email=twinops@localhost",
                "commit",
                "-m",
                msg,
            )
            # Exit 1 with "nothing to commit" is acceptable when re-applying.
            if committed_proc.returncode == 0:
                committed = True
                sha = _run_git(repo_root, "rev-parse", "HEAD")
                commit_sha = sha.stdout.strip() or None
            elif "nothing to commit" not in (committed_proc.stdout + committed_proc.stderr):
                raise RuntimeError(f"git commit failed: {committed_proc.stderr.strip()}")

    return ApplyResult(
        proposal_dir=source,
        target_dir=dest,
        branch=branch_name,
        committed=committed,
        commit_sha=commit_sha,
        files=files,
    )
