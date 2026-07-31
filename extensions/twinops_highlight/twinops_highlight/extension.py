"""Omniverse Kit extension entrypoint (optional runtime).

This file is not imported by unit tests. When loaded inside Kit it would:
1. Poll TwinOps /api/scene on a timer
2. Select / highlight drifted prims via omni.usd / kit commands

Without Kit installed, use ``python -m twinops_highlight.client`` instead.
"""

from __future__ import annotations

try:
    import omni.ext  # type: ignore
except ImportError:  # pragma: no cover - expected outside Omniverse
    omni = None  # type: ignore


if omni is not None:  # pragma: no cover

    class TwinOpsHighlightExtension(omni.ext.IExt):
        def on_startup(self, _ext_id: str) -> None:
            from twinops_highlight.client import TwinOpsHighlightClient

            self._client = TwinOpsHighlightClient()
            print("[twinops_highlight] started — polling TwinOps /api/scene")
            try:
                targets = self._client.highlight_targets()
                for line in self._client.apply_highlights(targets):
                    print(f"[twinops_highlight] {line}")
            except RuntimeError as exc:
                print(f"[twinops_highlight] waiting for TwinOps API: {exc}")

        def on_shutdown(self) -> None:
            print("[twinops_highlight] stopped")
