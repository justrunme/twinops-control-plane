"""Assembly-line MQTT-style telemetry simulator."""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass
from typing import Any

from twinops.telemetry.bus import TelemetryBus, TelemetryEvent


@dataclass
class SimulatorConfig:
    interval_seconds: float = 1.0
    base_temperature: float = 48.0
    spike_temperature: float = 88.0
    spike_every_cycles: int = 12


class AssemblyLineSimulator:
    """Publishes evolving factory telemetry onto a TelemetryBus."""

    def __init__(
        self,
        bus: TelemetryBus,
        *,
        config: SimulatorConfig | None = None,
        seed: int | None = 42,
    ) -> None:
        self.bus = bus
        self.config = config or SimulatorConfig()
        self._rng = random.Random(seed)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cycle = 0
        self._force_spike = False
        self._state: dict[str, Any] = {
            "robot_temp": self.config.base_temperature,
            "robot_status": "running",
            "robot_firmware": "4.12",
            "conveyor_speed": 1.2,
            "conveyor_status": "running",
            "scanner_status": "online",
        }

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def trigger_spike(self) -> None:
        self._force_spike = True

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="twinops-sim", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def tick(self) -> list[TelemetryEvent]:
        """Advance one simulation step and publish events."""
        self._cycle += 1
        spike = self._force_spike or (
            self.config.spike_every_cycles > 0
            and self._cycle % self.config.spike_every_cycles == 0
        )
        self._force_spike = False

        if spike:
            self._state["robot_temp"] = self.config.spike_temperature + self._rng.uniform(
                -1.0, 1.5
            )
            self._state["robot_status"] = "degraded"
            self._state["conveyor_speed"] = 1.8
        else:
            drift = self._rng.uniform(-1.5, 1.8)
            self._state["robot_temp"] = max(
                35.0, min(92.0, float(self._state["robot_temp"]) * 0.82 + (48.0 + drift) * 0.18)
            )
            if float(self._state["robot_temp"]) > 75:
                self._state["robot_status"] = "degraded"
            else:
                self._state["robot_status"] = "running"
            self._state["conveyor_speed"] = round(1.15 + self._rng.uniform(-0.05, 0.15), 2)

        events = [
            self._event(
                "factory/robot-01/temperature",
                "/World/Factory/LineA/Robot01",
                "twinops:temperature",
                round(float(self._state["robot_temp"]), 2),
            ),
            self._event(
                "factory/robot-01/status",
                "/World/Factory/LineA/Robot01",
                "twinops:status",
                self._state["robot_status"],
            ),
            self._event(
                "factory/robot-01/firmware",
                "/World/Factory/LineA/Robot01",
                "twinops:firmware",
                self._state["robot_firmware"],
            ),
            self._event(
                "factory/conveyor-01/speed",
                "/World/Factory/LineA/Conveyor01",
                "twinops:speed",
                self._state["conveyor_speed"],
            ),
            self._event(
                "factory/conveyor-01/status",
                "/World/Factory/LineA/Conveyor01",
                "twinops:status",
                self._state["conveyor_status"],
            ),
            self._event(
                "factory/scanner-01/status",
                "/World/Factory/LineA/Scanner01",
                "twinops:status",
                self._state["scanner_status"],
            ),
        ]
        for event in events:
            self.bus.publish(event)
        return events

    def snapshot_observations(self) -> dict[str, Any]:
        by_prim: dict[str, dict[str, Any]] = {}
        mapping = [
            ("/World/Factory/LineA/Robot01", "twinops:temperature", self._state["robot_temp"]),
            ("/World/Factory/LineA/Robot01", "twinops:status", self._state["robot_status"]),
            ("/World/Factory/LineA/Robot01", "twinops:firmware", self._state["robot_firmware"]),
            ("/World/Factory/LineA/Conveyor01", "twinops:speed", self._state["conveyor_speed"]),
            ("/World/Factory/LineA/Conveyor01", "twinops:status", self._state["conveyor_status"]),
            ("/World/Factory/LineA/Scanner01", "twinops:status", self._state["scanner_status"]),
        ]
        for prim, attr, value in mapping:
            by_prim.setdefault(prim, {})[attr] = value
        return {
            "timestamp": TelemetryBus.now(),
            "source": "twinops-simulator",
            "observations": [
                {"prim": prim, "attributes": attrs} for prim, attrs in sorted(by_prim.items())
            ],
        }

    def _event(
        self, topic: str, prim: str, attribute: str, value: Any
    ) -> TelemetryEvent:
        return TelemetryEvent(
            topic=topic,
            prim=prim,
            attribute=attribute,
            value=value,
            timestamp=TelemetryBus.now(),
        )

    def _run(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.config.interval_seconds)
