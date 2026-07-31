"""TwinOps scene runtime loop used by Kit extension and offline demos."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from twinops_highlight.apply import HighlightApplier, select_applier
from twinops_highlight.client import TwinOpsHighlightClient


@dataclass
class RuntimeTick:
    twin: str
    has_drift: bool
    targets: int
    notes: list[str] = field(default_factory=list)


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
    ) -> None:
        self.client = client or TwinOpsHighlightClient()
        self.applier = applier or select_applier(
            mode=apply_mode, overlay_path=overlay_path
        )
        self.prefer_ws = prefer_ws
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_tick: RuntimeTick | None = None

    def tick(self) -> RuntimeTick:
        if self.prefer_ws:
            frames = self.client.watch_scene_ws(frames=1)
            scene = frames[0] if frames else self.client.fetch_scene()
        else:
            scene = self.client.fetch_scene()
        targets = self.client.highlight_targets(scene)
        notes = (
            self.applier.clear()
            if not targets
            else self.applier.apply(targets)
        )
        result = RuntimeTick(
            twin=str(scene.get("twin") or ""),
            has_drift=bool(scene.get("hasDrift")),
            targets=len(targets),
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
                try:
                    self.tick()
                except Exception as exc:  # noqa: BLE001 - keep Kit loop alive
                    self.last_tick = RuntimeTick(
                        twin="",
                        has_drift=False,
                        targets=0,
                        notes=[f"ERROR {exc}"],
                    )
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
