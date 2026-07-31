"""Background loop: simulator → observed snapshot → drift → timeline."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from twinops.api.store import TwinStore
from twinops.composer import compose_digital_twin
from twinops.drift.engine import detect_drift
from twinops.drift.loaders import load_desired_state
from twinops.drift.model import ObservedState
from twinops.schema import load_manifest
from twinops.telemetry.bus import TelemetryBus
from twinops.telemetry.simulator import AssemblyLineSimulator, SimulatorConfig

logger = logging.getLogger(__name__)


class LiveDriftRuntime:
    def __init__(
        self,
        *,
        example_dir: Path,
        work_dir: Path,
        store: TwinStore,
        interval_seconds: float = 1.0,
        mqtt_host: str | None = None,
        mqtt_port: int = 1883,
    ) -> None:
        self.example_dir = example_dir.resolve()
        self.work_dir = work_dir.resolve()
        self.store = store
        self.interval_seconds = interval_seconds
        self.bus = TelemetryBus()
        self.simulator = AssemblyLineSimulator(
            self.bus,
            config=SimulatorConfig(
                interval_seconds=interval_seconds,
                # Drift loop drives ticks; keep sim thread as optional publisher only.
            ),
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._stage_root: Path | None = None
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._ws_clients: list[Any] = []
        self._ws_lock = threading.Lock()

    def bootstrap(self) -> None:
        manifest = load_manifest(self.example_dir / "twin.yaml")
        stage_dir = self.work_dir / "stage"
        result = compose_digital_twin(manifest, stage_dir)
        if not result.ok:
            raise RuntimeError("failed to compose demo stage for live runtime")

        # Inject stale PLM revision so drift is visible immediately.
        plm = result.files["plm_overlay"]
        text = plm.read_text(encoding="utf-8")
        parts = text.split('over "Robot01"')
        if len(parts) == 2:
            robot = parts[1].replace(
                'twinops:plmRevision = "C"', 'twinops:plmRevision = "B"', 1
            )
            plm.write_text(parts[0] + 'over "Robot01"' + robot, encoding="utf-8")

        self._stage_root = result.files["root"]
        self.store.set_twin_meta(
            {
                "name": manifest.name,
                "manifest": str(self.example_dir / "twin.yaml"),
                "stage": str(self._stage_root),
                "variant": manifest.variant,
            }
        )
        if self._mqtt_host:
            self.bus.enable_mqtt(self._mqtt_host, self._mqtt_port)

        # Seed first drift evaluation.
        self.evaluate_drift()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="twinops-live-drift", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def trigger_spike(self) -> dict[str, Any]:
        self.simulator.trigger_spike()
        events = self.simulator.tick()
        report = self.evaluate_drift(record_telemetry=True)
        return {"events": len(events), "drift": report}

    def register_ws(self, client: Any) -> None:
        with self._ws_lock:
            self._ws_clients.append(client)

    def unregister_ws(self, client: Any) -> None:
        with self._ws_lock:
            if client in self._ws_clients:
                self._ws_clients.remove(client)

    def evaluate_drift(self, *, record_telemetry: bool = False) -> dict[str, Any]:
        if self._stage_root is None:
            raise RuntimeError("runtime not bootstrapped")

        observed_raw = self.simulator.snapshot_observations()
        observed = ObservedState(
            timestamp=observed_raw.get("timestamp"),
            source=observed_raw.get("source"),
            attributes_by_prim={
                item["prim"]: item["attributes"]
                for item in observed_raw.get("observations", [])
            },
        )
        report = detect_drift(
            desired=load_desired_state(self.example_dir / "desired.yaml"),
            stage=self._stage_root,
            observed=observed,
            manifest=self.example_dir / "twin.yaml",
        )
        payload = report.to_dict()
        self.store.set_observed(observed_raw)
        self.store.set_drift(payload)
        self.store.set_simulator_state(self.simulator.state)

        if record_telemetry:
            state = self.simulator.state
            tel = self.store.record(
                event_type="telemetry",
                timestamp=str(observed_raw.get("timestamp")),
                summary=(
                    f"Robot01 temp={state.get('robot_temp')} "
                    f"status={state.get('robot_status')} "
                    f"fw={state.get('robot_firmware')}"
                ),
                payload={"state": state},
            )
            self._broadcast({"type": "telemetry", "event": tel.to_dict()})

        summary = ", ".join(
            f"{key}={value}" for key, value in sorted(report.summary.items())
        ) or "no findings"
        event = self.store.record(
            event_type="drift",
            timestamp=report.generated_at,
            summary=f"{'DRIFT' if report.has_drift else 'SYNCED'} · {summary}",
            payload={
                "hasDrift": report.has_drift,
                "summary": report.summary,
                "findings": payload["status"]["findings"][:12],
            },
        )
        self._broadcast(
            {
                "type": "drift",
                "event": event.to_dict(),
                "snapshot": self.store.snapshot(),
            }
        )
        return payload

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.simulator.tick()
                self.evaluate_drift(record_telemetry=True)
            except Exception:  # noqa: BLE001
                logger.exception("live drift evaluation failed")
            self._stop.wait(self.interval_seconds)

    def _broadcast(self, message: dict[str, Any]) -> None:
        with self._ws_lock:
            clients = list(self._ws_clients)
        stale: list[Any] = []
        for client in clients:
            try:
                client.send_json(message)
            except Exception:  # noqa: BLE001
                stale.append(client)
        for client in stale:
            self.unregister_ws(client)
