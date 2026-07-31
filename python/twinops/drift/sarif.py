"""Export TwinOps drift findings as SARIF 2.1.0 for CI / code scanning UIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from twinops import __version__
from twinops.drift.engine import DriftReport
from twinops.drift.model import DriftFinding

_LEVEL = {
    "CRITICAL": "error",
    "DRIFT": "error",
    "MISSING": "error",
    "WARNING": "warning",
    "SYNCED": "note",
}


def finding_to_result(finding: DriftFinding) -> dict[str, Any] | None:
    if finding.status == "SYNCED":
        return None
    level = _LEVEL.get(finding.status, "warning")
    rule_id = f"twinops-drift/{finding.status.lower()}"
    message = finding.message or (
        f"{finding.short_prim}.{finding.attribute}: desired={finding.desired} "
        f"rendered={finding.rendered} observed={finding.observed}"
    )
    return {
        "ruleId": rule_id,
        "level": level,
        "message": {"text": message},
        "locations": [
            {
                "logicalLocations": [
                    {
                        "fullyQualifiedName": f"{finding.prim}#{finding.attribute}",
                        "kind": "prim",
                    }
                ]
            }
        ],
        "properties": {
            "prim": finding.prim,
            "attribute": finding.attribute,
            "status": finding.status,
            "severity": finding.severity,
            "desired": finding.desired,
            "rendered": finding.rendered,
            "observed": finding.observed,
        },
    }


def report_to_sarif(report: DriftReport) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for finding in report.findings:
        item = finding_to_result(finding)
        if item is not None:
            results.append(item)

    rules = []
    for status, level in (
        ("critical", "error"),
        ("drift", "error"),
        ("missing", "error"),
        ("warning", "warning"),
    ):
        rules.append(
            {
                "id": f"twinops-drift/{status}",
                "shortDescription": {"text": f"TwinOps {status} finding"},
                "defaultConfiguration": {"level": level},
                "helpUri": "https://github.com/justrunme/twinops-control-plane/blob/main/docs/architecture.md",
            }
        )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "twinopsctl",
                        "version": __version__,
                        "informationUri": "https://github.com/justrunme/twinops-control-plane",
                        "rules": rules,
                    }
                },
                "results": results,
                "properties": {
                    "twinName": report.name,
                    "generatedAt": report.generated_at,
                    "hasDrift": report.has_drift,
                    "summary": report.summary,
                },
            }
        ],
    }


def write_sarif_report(report: DriftReport, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report_to_sarif(report), indent=2) + "\n", encoding="utf-8")
    return out
