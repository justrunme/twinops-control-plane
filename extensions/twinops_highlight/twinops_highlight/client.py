"""GPU-free TwinOps highlight client used by the Kit extension stub.

Inside Omniverse Kit this client would drive selection / emissive materials.
Outside Kit it remains a plain HTTP poller so CI and demos work on any laptop.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HighlightTarget:
    prim: str
    status: str
    color: list[float]
    intensity: float
    message: str


class TwinOpsHighlightClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8080", *, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_scene(self) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}/api/scene",
            headers={"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"failed to fetch TwinOps scene: {exc}") from exc

    def highlight_targets(self, scene: dict[str, Any] | None = None) -> list[HighlightTarget]:
        payload = scene if scene is not None else self.fetch_scene()
        targets: list[HighlightTarget] = []
        for item in payload.get("prims") or []:
            highlight = item.get("highlight") or {}
            if not highlight.get("enabled"):
                continue
            findings = item.get("findings") or []
            message = ""
            if findings:
                message = str(findings[0].get("message") or "")
            targets.append(
                HighlightTarget(
                    prim=str(item.get("prim") or ""),
                    status=str(item.get("status") or "DRIFT"),
                    color=[float(v) for v in highlight.get("color") or [0.86, 0.15, 0.15]],
                    intensity=float(highlight.get("intensity") or 0.8),
                    message=message,
                )
            )
        return targets

    def apply_highlights(self, targets: list[HighlightTarget]) -> list[str]:
        """Stub apply step — replace with omni.kit.commands when running in Kit."""
        return [format_highlight_plan(target) for target in targets]


def format_highlight_plan(target: HighlightTarget) -> str:
    color = ",".join(f"{channel:.2f}" for channel in target.color)
    return (
        f"HIGHLIGHT {target.prim} status={target.status} "
        f"color=[{color}] intensity={target.intensity:.2f}"
        + (f" :: {target.message}" if target.message else "")
    )


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Poll TwinOps /api/scene and print highlight plan")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()

    client = TwinOpsHighlightClient(args.base_url)
    try:
        scene = client.fetch_scene()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc

    targets = client.highlight_targets(scene)
    print(f"twin={scene.get('twin')} hasDrift={scene.get('hasDrift')} targets={len(targets)}")
    for line in client.apply_highlights(targets):
        print(line)
    if not targets:
        print("No drifted prims to highlight.")


if __name__ == "__main__":
    main()
