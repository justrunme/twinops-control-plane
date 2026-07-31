"""Background loop: simulator → observed snapshot → drift → timeline."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from twinops.api.store import TwinStore
from twinops.composer import compose_digital_twin
from twinops.drift.engine import DriftReport, detect_drift
from twinops.drift.html_report import render_html_report
from twinops.drift.loaders import load_desired_state
from twinops.drift.model import ObservedState
from twinops.drift.reconcile import propose_reconciliation
from twinops.scene import build_scene_snapshot
from twinops.schema import load_manifest
from twinops.telemetry.bus import TelemetryBus
from twinops.telemetry.ingest import ObservationIngest
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
        mqtt_ingest: bool = True,
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
        self.ingest = ObservationIngest()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._stage_root: Path | None = None
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._mqtt_ingest = mqtt_ingest
        self._ws_clients: list[Any] = []
        self._ws_lock = threading.Lock()
        self._stage_dir: Path | None = None
        self._last_report: DriftReport | None = None

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

        self._stage_dir = stage_dir
        self._stage_root = result.files["root"]
        self.store.set_twin_meta(
            {
                "name": manifest.name,
                "manifest": str(self.example_dir / "twin.yaml"),
                "stage": str(self._stage_root),
                "variant": manifest.variant,
                "reconciled": False,
            }
        )
        self.ingest = ObservationIngest.from_manifest_mappings(manifest.telemetry_mappings)
        if self._mqtt_host:
            self.bus.enable_mqtt(self._mqtt_host, self._mqtt_port)
            if self._mqtt_ingest and self.ingest.topics:
                self.bus.enable_mqtt_ingest(
                    self._mqtt_host,
                    self._mqtt_port,
                    topics=self.ingest.topics,
                    handler=self._on_mqtt_ingest,
                )

        # Seed first drift evaluation.
        self.evaluate_drift()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="twinops-live-drift", daemon=True
        )
        self._thread.start()

    def mqtt_status(self) -> dict[str, Any]:
        endpoint = self.bus.mqtt_endpoint
        ingest = self.ingest.status()
        ingest["enabled"] = self.bus.mqtt_ingest_enabled
        ingest["requested"] = bool(self._mqtt_host and self._mqtt_ingest)
        return {
            "requested": bool(self._mqtt_host),
            "enabled": self.bus.mqtt_enabled,
            "host": self._mqtt_host,
            "port": self._mqtt_port if self._mqtt_host else None,
            "endpoint": endpoint,
            "ingest": ingest,
        }

    def scene_snapshot(self) -> dict[str, Any]:
        """Prim highlight tree for web UI / Omniverse Kit consumers."""
        drift = self.store.latest_drift or {}
        status = drift.get("status") or {}
        findings = list(status.get("findings") or [])
        meta = drift.get("metadata") or {}
        twin_name = str(self.store.twin_meta.get("name") or "unknown")
        return build_scene_snapshot(
            twin_name=twin_name,
            findings=findings,
            generated_at=meta.get("generatedAt"),
        )

    def drift_html(self) -> str:
        if self._last_report is None:
            self.evaluate_drift(record_telemetry=False)
        assert self._last_report is not None
        return render_html_report(self._last_report)

    def metrics(self) -> dict[str, Any]:
        drift = self.store.latest_drift or {}
        status = drift.get("status") or {}
        summary = status.get("summary") or {}
        scene = self.scene_snapshot()
        lit = sum(
            1
            for prim in scene.get("prims") or []
            if (prim.get("highlight") or {}).get("enabled")
        )
        mqtt = self.mqtt_status()
        ingest = mqtt.get("ingest") or {}
        return {
            "twin": self.store.twin_meta.get("name"),
            "hasDrift": bool(status.get("hasDrift")),
            "summary": summary,
            "highlightedPrims": lit,
            "timelineEvents": len(self.store.timeline(limit=200)),
            "reconciled": bool(self.store.twin_meta.get("reconciled")),
            "mqttPublishEnabled": bool(mqtt.get("enabled")),
            "mqttIngestReceived": int(ingest.get("received") or 0),
            "robotTemp": self.simulator.state.get("robot_temp"),
        }

    def metrics_prometheus(self) -> str:
        m = self.metrics()
        summary = m.get("summary") or {}
        lines = [
            "# HELP twinops_drift_has_drift Whether the latest evaluation has drift (1/0).",
            "# TYPE twinops_drift_has_drift gauge",
            f"twinops_drift_has_drift {1 if m.get('hasDrift') else 0}",
            "# HELP twinops_drift_findings Drift findings by status.",
            "# TYPE twinops_drift_findings gauge",
        ]
        for key in ("SYNCED", "WARNING", "MISSING", "DRIFT", "CRITICAL"):
            lines.append(
                f'twinops_drift_findings{{status="{key}"}} {int(summary.get(key) or 0)}'
            )
        lines.extend(
            [
                "# HELP twinops_scene_highlighted_prims Prim count with highlight.enabled.",
                "# TYPE twinops_scene_highlighted_prims gauge",
                f"twinops_scene_highlighted_prims {int(m.get('highlightedPrims') or 0)}",
                "# HELP twinops_mqtt_ingest_received_total External MQTT messages applied.",
                "# TYPE twinops_mqtt_ingest_received_total counter",
                f"twinops_mqtt_ingest_received_total {int(m.get('mqttIngestReceived') or 0)}",
                "# HELP twinops_robot_temperature_celsius Latest Robot01 temperature.",
                "# TYPE twinops_robot_temperature_celsius gauge",
                f"twinops_robot_temperature_celsius {float(m.get('robotTemp') or 0)}",
                "",
            ]
        )
        return "\n".join(lines)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self.bus.disable_mqtt()

    def trigger_spike(self) -> dict[str, Any]:
        self.simulator.trigger_spike()
        events = self.simulator.tick()
        report = self.evaluate_drift(record_telemetry=True)
        return {"events": len(events), "drift": report}

    def reconcile(self) -> dict[str, Any]:
        """Generate proposal, apply USD overlay, heal observed state, re-check drift."""
        if self._stage_root is None or self._stage_dir is None:
            raise RuntimeError("runtime not bootstrapped")

        # Ensure we reconcile against the freshest three-way view.
        before = self.evaluate_drift(record_telemetry=False)
        if self._last_report is None:
            raise RuntimeError("drift report unavailable")

        proposal_dir = self.work_dir / "proposal"
        proposal = propose_reconciliation(self._last_report, proposal_dir)
        applied = self._apply_proposal_overlay(proposal.overlay_path)

        self.ingest.clear()
        healed = self.simulator.heal(firmware="4.14", cooldown_cycles=25)
        self.simulator.tick()

        after = self.evaluate_drift(record_telemetry=True)
        proposal_payload = proposal.to_dict()
        proposal_payload["status"]["applied"] = True
        proposal_payload["status"]["appliedOverlay"] = str(applied)
        proposal_payload["status"]["healedSimulator"] = healed
        proposal_payload["status"]["driftBefore"] = before.get("status", {}).get("summary", {})
        proposal_payload["status"]["driftAfter"] = after.get("status", {}).get("summary", {})
        self.store.set_proposal(proposal_payload)

        meta = dict(self.store.twin_meta)
        meta["reconciled"] = True
        meta["lastReconcileOverlay"] = str(applied)
        self.store.set_twin_meta(meta)

        event = self.store.record(
            event_type="reconcile",
            timestamp=str(after.get("metadata", {}).get("generatedAt")),
            summary=(
                f"Applied reconciliation ({len(proposal.changes)} changes) · "
                f"drift={'yes' if after.get('status', {}).get('hasDrift') else 'reduced'}"
            ),
            payload={
                "changes": proposal.changes,
                "overlay": str(applied),
                "healed": healed,
            },
        )
        self._broadcast(
            {
                "type": "reconcile",
                "event": event.to_dict(),
                "snapshot": self.store.snapshot(),
                "scene": self.scene_snapshot(),
            }
        )
        return {
            "proposal": proposal_payload,
            "drift": after,
            "healed": healed,
            "changes": len(proposal.changes),
            "scene": self.scene_snapshot(),
        }

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

        observed_raw = self.ingest.merge_observations(self.simulator.snapshot_observations())
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
        self._last_report = report
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
                "scene": self.scene_snapshot(),
            }
        )
        return payload

    def _on_mqtt_ingest(self, topic: str, payload: bytes) -> None:
        applied = self.ingest.handle_message(topic, payload)
        if not applied:
            return
        binding = self.ingest.binding_for(topic)
        if binding is None:
            return
        self.simulator.apply_external(
            binding.prim, binding.attribute, self.ingest.status().get("lastValue")
        )
        try:
            self.evaluate_drift(record_telemetry=True)
        except Exception:  # noqa: BLE001
            logger.exception("drift evaluation after mqtt ingest failed")

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

    def _apply_proposal_overlay(self, overlay_path: Path) -> Path:
        assert self._stage_dir is not None
        assert self._stage_root is not None

        target = self._stage_dir / "reconcile-overlay.usda"
        target.write_text(overlay_path.read_text(encoding="utf-8"), encoding="utf-8")

        # Also restore PLM revision in the composed PLM overlay for strong demos.
        plm = self._stage_dir / "plm-overlay.usda"
        if plm.is_file():
            text = plm.read_text(encoding="utf-8")
            parts = text.split('over "Robot01"')
            if len(parts) == 2:
                robot = parts[1].replace(
                    'twinops:plmRevision = "B"',
                    'twinops:plmRevision = "C"',
                    1,
                )
                plm.write_text(parts[0] + 'over "Robot01"' + robot, encoding="utf-8")

        root_text = self._stage_root.read_text(encoding="utf-8")
        if "reconcile-overlay.usda" not in root_text:
            root_text = root_text.replace(
                "    subLayers = [\n",
                "    subLayers = [\n        @./reconcile-overlay.usda@\n",
                1,
            )
            self._stage_root.write_text(root_text, encoding="utf-8")
        return target
