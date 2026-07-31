"""TwinOps scene runtime loop used by Kit extension and offline demos."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from twinops_highlight.apply import HighlightApplier, KitUsdApplier, select_applier
from twinops_highlight.client import TwinOpsHighlightClient
from twinops_highlight.session import RuntimeState, SessionHighlightLayer


@dataclass
class RuntimeTick:
    twin: str
    has_drift: bool
    targets: int
    state: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "twin": self.twin,
            "hasDrift": self.has_drift,
            "targets": self.targets,
            "state": self.state,
            "notes": list(self.notes),
        }


class TwinOpsSceneRuntime:
    """Poll TwinOps scene contract and apply highlights through a backend."""

    def __init__(
        self,
        client: TwinOpsHighlightClient | None = None,
        *,
        applier: HighlightApplier | None = None,
        apply_mode: str = "auto",
        overlay_path: str | None = None,
        prefer_ws: bool = False,
        stale_after_failures: int = 3,
    ) -> None:
        self.client = client or TwinOpsHighlightClient()
        self.applier = applier or select_applier(
            mode=apply_mode, overlay_path=overlay_path
        )
        self.prefer_ws = prefer_ws
        self.stale_after_failures = max(1, stale_after_failures)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_tick: RuntimeTick | None = None
        self.state = RuntimeState.CONNECTED
        self._failures = 0
        self._session = self._resolve_session_layer()

    def _resolve_session_layer(self) -> SessionHighlightLayer:
        if isinstance(self.applier, KitUsdApplier):
            return self.applier.session
        return SessionHighlightLayer()

    def tick(self) -> RuntimeTick:
        try:
            if self.prefer_ws:
                frames = self.client.watch_scene_ws(frames=1)
                scene = frames[0] if frames else self.client.fetch_scene()
            else:
                scene = self.client.fetch_scene()
            if self._failures > 0:
                # Recover session overrides after a transient disconnect.
                if hasattr(self.applier, "restore_after_reconnect"):
                    self.applier.restore_after_reconnect()  # type: ignore[union-attr]
                self.state = RuntimeState.CONNECTED
            self._failures = 0
        except Exception as exc:  # noqa: BLE001 - keep Kit loop alive
            self._failures += 1
            if self._failures >= self.stale_after_failures:
                self.state = RuntimeState.STALE
                self._session.mark_stale()
            else:
                self.state = RuntimeState.RECONNECTING
                self._session.mark_reconnecting()
            result = RuntimeTick(
                twin="",
                has_drift=False,
                targets=0,
                state=self.state.value,
                notes=[f"ERROR {exc}"],
            )
            self.last_tick = result
            return result

        targets = self.client.highlight_targets(scene)
        notes = (
            self.applier.clear()
            if not targets
            else self.applier.apply(targets)
        )
        if isinstance(self.applier, KitUsdApplier):
            self.state = self.applier.session.state
        else:
            self.state = (
                RuntimeState.HIGHLIGHT_CLEARED
                if not targets
                else RuntimeState.HIGHLIGHT_APPLIED
            )
        result = RuntimeTick(
            twin=str(scene.get("twin") or ""),
            has_drift=bool(scene.get("hasDrift")),
            targets=len(targets),
            state=self.state.value,
            notes=notes,
        )
        self.last_tick = result
        return result

    def start(self, *, interval_seconds: float = 1.0) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.is_set():
                self.tick()
                self._stop.wait(max(0.2, interval_seconds))

        self._thread = threading.Thread(
            target=_loop, name="twinops-scene-runtime", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        try:
            self.applier.clear()
        except Exception:  # noqa: BLE001
            pass


def run_once(
    *,
    base_url: str = "http://127.0.0.1:8080",
    token: str | None = None,
    apply_mode: str = "auto",
    overlay_path: str | None = None,
) -> RuntimeTick:
    runtime = TwinOpsSceneRuntime(
        TwinOpsHighlightClient(base_url, token=token),
        apply_mode=apply_mode,
        overlay_path=overlay_path,
    )
    return runtime.tick()
