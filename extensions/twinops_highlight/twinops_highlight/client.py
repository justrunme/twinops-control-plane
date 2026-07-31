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
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        *,
        timeout: float = 5.0,
        token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = (token or "").strip() or None

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get_json(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"failed to fetch TwinOps {path}: {exc}") from exc

    def fetch_scene(self) -> dict[str, Any]:
        return self._get_json("/api/scene")

    def fetch_streaming_session(self) -> dict[str, Any]:
        """Fetch mock (or future real) Kit App Streaming session descriptor."""
        return self._get_json("/api/streaming/session")

    def watch_scene(self, *, interval_seconds: float = 1.0, ticks: int = 1) -> list[dict[str, Any]]:
        """Poll scene snapshots (WS client optional; poll works without extra deps)."""
        import time

        frames: list[dict[str, Any]] = []
        for index in range(max(1, ticks)):
            if index:
                time.sleep(max(0.0, interval_seconds))
            frames.append(self.fetch_scene())
        return frames

    def watch_scene_ws(self, *, frames: int = 1, timeout: float = 5.0) -> list[dict[str, Any]]:
        """Consume scene snapshots from `/ws/events` when `websockets` is installed.

        Falls back to a single HTTP poll when the optional dependency is missing.
        """
        try:
            import asyncio

            import websockets
        except ImportError:
            return self.watch_scene(ticks=max(1, frames))

        ws_base = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        url = f"{ws_base}/ws/events"
        if self.token:
            url = f"{url}?token={self.token}"

        async def _collect() -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            async with websockets.connect(url, open_timeout=timeout) as socket:
                while len(out) < max(1, frames):
                    raw = await asyncio.wait_for(socket.recv(), timeout=timeout)
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    message = json.loads(raw)
                    scene = message.get("scene")
                    if isinstance(scene, dict):
                        out.append(scene)
                    elif message.get("type") == "snapshot" and isinstance(
                        message.get("snapshot"), dict
                    ):
                        # Snapshot frames always include scene in TwinOps live API.
                        maybe = message.get("scene")
                        if isinstance(maybe, dict):
                            out.append(maybe)
            return out

        try:
            return asyncio.run(_collect())
        except Exception:
            return self.watch_scene(ticks=max(1, frames))

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

    def apply_highlights(
        self,
        targets: list[HighlightTarget],
        *,
        mode: str = "auto",
        overlay_path: str | None = None,
    ) -> list[str]:
        """Apply highlights through plan / USD overlay / Kit backend."""
        from twinops_highlight.apply import select_applier

        applier = select_applier(mode=mode, overlay_path=overlay_path)
        if not targets:
            return applier.clear()
        return applier.apply(targets)


def format_highlight_plan(target: HighlightTarget) -> str:
    color = ",".join(f"{channel:.2f}" for channel in target.color)
    return (
        f"HIGHLIGHT {target.prim} status={target.status} "
        f"color=[{color}] intensity={target.intensity:.2f}"
        + (f" :: {target.message}" if target.message else "")
    )


def main() -> None:
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(description="Poll TwinOps /api/scene and print highlight plan")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--token",
        default=os.environ.get("TWINOPS_API_TOKEN"),
        help="optional bearer token (or TWINOPS_API_TOKEN)",
    )
    parser.add_argument(
        "--session",
        action="store_true",
        help="also print GET /api/streaming/session descriptor",
    )
    parser.add_argument(
        "--watch",
        type=int,
        default=1,
        metavar="N",
        help="poll scene N times (default: 1)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="seconds between --watch polls",
    )
    parser.add_argument(
        "--ws",
        action="store_true",
        help="prefer /ws/events scene frames (falls back to HTTP poll)",
    )
    parser.add_argument(
        "--apply",
        choices=("auto", "plan", "overlay", "kit"),
        default="plan",
        help="highlight apply backend (default: plan)",
    )
    parser.add_argument(
        "--overlay-out",
        default="/tmp/twinops-highlight-overlay.usda",
        help="USDA path when --apply overlay",
    )
    args = parser.parse_args()

    client = TwinOpsHighlightClient(args.base_url, token=args.token)
    try:
        if args.session:
            session = client.fetch_streaming_session()
            print(
                f"session mode={session.get('metadata', {}).get('mode')} "
                f"phase={session.get('status', {}).get('phase')} "
                f"streamUrl={session.get('spec', {}).get('streamUrl')}"
            )
        if args.ws:
            frames = client.watch_scene_ws(frames=args.watch)
        else:
            frames = client.watch_scene(interval_seconds=args.interval, ticks=args.watch)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc

    for index, scene in enumerate(frames, start=1):
        targets = client.highlight_targets(scene)
        prefix = f"[{index}/{len(frames)}] " if len(frames) > 1 else ""
        print(
            f"{prefix}twin={scene.get('twin')} hasDrift={scene.get('hasDrift')} "
            f"targets={len(targets)}"
        )
        for line in client.apply_highlights(
            targets, mode=args.apply, overlay_path=args.overlay_out
        ):
            print(line)
        if not targets:
            print(f"{prefix}No drifted prims to highlight.")


if __name__ == "__main__":
    main()
