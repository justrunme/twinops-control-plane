"""Generate GitOps reconciliation proposals from drift findings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from twinops.composer import usda
from twinops.drift.engine import DriftReport
from twinops.drift.model import DriftFinding


@dataclass
class ReconciliationProposal:
    output_dir: Path
    overlay_path: Path
    proposal_path: Path
    summary_path: Path
    changes: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": "twinops.io/v1alpha1",
            "kind": "ReconciliationProposal",
            "metadata": {
                "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
            "spec": {
                "overlay": str(self.overlay_path),
                "changes": self.changes,
            },
            "status": {
                "recommendedBranch": "reconcile/twinops-auto",
                "recommendedAction": "open-pull-request",
                "notes": [
                    "Review generated USD overlay before merge",
                    "Operator apply path is planned for Milestone 3",
                ],
            },
        }


def propose_reconciliation(
    report: DriftReport,
    output_dir: str | Path,
) -> ReconciliationProposal:
    """Create an overlay that restores desired values for drifted attributes."""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    # Prefer one change per prim/attribute; CRITICAL policy rows do not rewrite desired.
    actionable = [
        finding
        for finding in report.findings
        if finding.status == "DRIFT"
        and finding.desired is not None
        and finding.attribute != "telemetry"
        and not str(finding.desired).startswith("<=")
    ]

    # Deduplicate by prim+attribute keeping first (highest severity sort already applied).
    selected: dict[tuple[str, str], DriftFinding] = {}
    for finding in actionable:
        key = (finding.prim, finding.attribute)
        selected.setdefault(key, finding)

    items: list[tuple[str, str, Any]] = []
    changes: list[dict[str, Any]] = []
    for finding in selected.values():
        items.append((finding.prim, finding.attribute, finding.desired))
        changes.append(
            {
                "prim": finding.prim,
                "attribute": finding.attribute,
                "fromRendered": finding.rendered,
                "fromObserved": finding.observed,
                "toDesired": finding.desired,
                "reason": finding.message,
            }
        )

    # Operational hint: critical temperature → suggest maintenance variant marker.
    if any(item.status == "CRITICAL" for item in report.findings):
        items.append(
            (
                "/World/Factory/LineA",
                "twinops:recommendedVariant",
                "maintenance",
            )
        )
        changes.append(
            {
                "prim": "/World/Factory/LineA",
                "attribute": "twinops:recommendedVariant",
                "toDesired": "maintenance",
                "reason": "critical telemetry threshold exceeded",
            }
        )

    overlay = usda.build_overlay_layer(
        doc=f"TwinOps reconciliation proposal for {report.name}",
        prims=usda.group_attributes_by_prim(items) if items else [],
    )
    if not items:
        overlay = (
            "#usda 1.0\n(\n"
            f'    doc = "TwinOps reconciliation proposal for {report.name} (no changes)"\n'
            ")\n"
        )

    overlay_path = out / "reconcile-overlay.usda"
    proposal_path = out / "reconciliation-proposal.json"
    summary_path = out / "PULL_REQUEST.md"

    overlay_path.write_text(overlay, encoding="utf-8")

    proposal = ReconciliationProposal(
        output_dir=out,
        overlay_path=overlay_path,
        proposal_path=proposal_path,
        summary_path=summary_path,
        changes=changes,
    )
    proposal_path.write_text(
        json.dumps(proposal.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    summary_path.write_text(_render_pr_markdown(report, changes), encoding="utf-8")
    return proposal


def _render_pr_markdown(report: DriftReport, changes: list[dict[str, Any]]) -> str:
    lines = [
        f"# TwinOps reconciliation — {report.name}",
        "",
        "Proposed GitOps change generated from three-way drift detection.",
        "",
        "## Summary",
        "",
    ]
    if not changes:
        lines.append("- No overlay changes required.")
    else:
        for change in changes:
            attr = str(change["attribute"]).removeprefix("twinops:")
            prim = change["prim"].rsplit("/", 1)[-1]
            lines.append(
                f"- `{prim}` `{attr}` → `{change.get('toDesired')}` "
                f"({change.get('reason')})"
            )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- `reconcile-overlay.usda`",
            "- `reconciliation-proposal.json`",
            "",
            "## Test plan",
            "",
            "- [ ] Review overlay attributes",
            "- [ ] Re-run `twinopsctl build`",
            "- [ ] Re-run `twinopsctl drift` and confirm SYNCED / improved state",
            "",
        ]
    )
    return "\n".join(lines)
