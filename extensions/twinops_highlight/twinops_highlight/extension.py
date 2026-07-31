"""Omniverse Kit extension — TwinOps scene runtime.

Loads inside Kit, polls/consumes TwinOps highlight contract, and applies
displayColor + selection on drifted prims. Outside Kit this module is inert;
use ``python -m twinops_highlight.client`` or ``runtime.run_once``.
"""

from __future__ import annotations

import os

try:
    import omni.ext  # type: ignore
    import omni.kit.app  # type: ignore
except ImportError:  # pragma: no cover - expected outside Omniverse
    omni = None  # type: ignore


if omni is not None:  # pragma: no cover

    class TwinOpsHighlightExtension(omni.ext.IExt):
        def on_startup(self, _ext_id: str) -> None:
            from twinops_highlight.apply import KitUsdApplier
            from twinops_highlight.client import TwinOpsHighlightClient
            from twinops_highlight.runtime import TwinOpsSceneRuntime

            base_url = os.environ.get("TWINOPS_API_URL", "http://127.0.0.1:8080")
            token = os.environ.get("TWINOPS_API_TOKEN")
            interval = float(os.environ.get("TWINOPS_POLL_INTERVAL", "1.0"))
            prefer_ws = os.environ.get("TWINOPS_PREFER_WS", "").lower() in {
                "1",
                "true",
                "yes",
            }

            self._runtime = TwinOpsSceneRuntime(
                TwinOpsHighlightClient(base_url, token=token),
                applier=KitUsdApplier(),
                prefer_ws=prefer_ws,
            )
            print(
                f"[twinops_highlight] runtime start url={base_url} "
                f"interval={interval}s ws={prefer_ws}"
            )
            try:
                tick = self._runtime.tick()
                for note in tick.notes:
                    print(f"[twinops_highlight] {note}")
            except Exception as exc:  # noqa: BLE001
                print(f"[twinops_highlight] waiting for TwinOps API: {exc}")

            self._runtime.start(interval_seconds=interval)

            # Also register an update subscription as a Kit-native heartbeat.
            self._update_sub = None
            try:
                import carb  # type: ignore

                app = omni.kit.app.get_app()
                stream = app.get_update_event_stream()

                def _on_update(_e) -> None:  # type: ignore[no-untyped-def]
                    # Lightweight status line; heavy work stays on the runtime thread.
                    tick = self._runtime.last_tick
                    if tick and tick.notes:
                        carb.log_info(
                            f"[twinops] twin={tick.twin} drift={tick.has_drift} "
                            f"targets={tick.targets}"
                        )

                self._update_sub = stream.create_subscription_to_pop(
                    _on_update, name="twinops_highlight"
                )
            except Exception:  # noqa: BLE001
                self._update_sub = None

        def on_shutdown(self) -> None:
            if getattr(self, "_update_sub", None) is not None:
                self._update_sub = None
            if getattr(self, "_runtime", None) is not None:
                self._runtime.stop()
            print("[twinops_highlight] stopped")
