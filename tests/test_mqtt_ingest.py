from twinops.telemetry.bus import TelemetryBus
from twinops.telemetry.ingest import ObservationIngest, TopicBinding
from twinops.telemetry.simulator import AssemblyLineSimulator


def test_observation_ingest_applies_external_and_ignores_twinops_echo() -> None:
    ingest = ObservationIngest(
        [
            TopicBinding(
                topic="factory/robot-01/temperature",
                prim="/World/Factory/LineA/Robot01",
                attribute="twinops:temperature",
            )
        ]
    )
    assert ingest.handle_message(
        "factory/robot-01/temperature",
        b'{"value": 91.5, "source": "factory-plc"}',
    )
    assert ingest.received == 1
    assert ingest.handle_message(
        "factory/robot-01/temperature",
        b'{"value": 42.0, "source": "twinops"}',
    ) is False
    assert ingest.ignored == 1

    base = {
        "timestamp": "t0",
        "source": "twinops-simulator",
        "observations": [
            {
                "prim": "/World/Factory/LineA/Robot01",
                "attributes": {"twinops:temperature": 42.0, "twinops:status": "running"},
            }
        ],
    }
    merged = ingest.merge_observations(base)
    attrs = merged["observations"][0]["attributes"]
    assert attrs["twinops:temperature"] == 91.5
    assert attrs["twinops:status"] == "running"


def test_simulator_external_lock_survives_tick() -> None:
    sim = AssemblyLineSimulator(TelemetryBus(), seed=1)
    assert sim.apply_external(
        "/World/Factory/LineA/Robot01", "twinops:temperature", 91.0
    )
    sim.tick()
    assert float(sim.state["robot_temp"]) == 91.0


def test_plain_scalar_mqtt_payload() -> None:
    ingest = ObservationIngest(
        [
            TopicBinding(
                topic="factory/robot-01/status",
                prim="/World/Factory/LineA/Robot01",
                attribute="twinops:status",
            )
        ]
    )
    assert ingest.handle_message("factory/robot-01/status", b"degraded")
    assert ingest.last_value == "degraded"


def test_strict_schema_rejects_bad_schema_objects() -> None:
    ingest = ObservationIngest(
        [
            TopicBinding(
                topic="factory/robot-01/temperature",
                prim="/World/Factory/LineA/Robot01",
                attribute="twinops:temperature",
            )
        ],
        strict_schema=True,
    )
    assert (
        ingest.handle_message(
            "factory/robot-01/temperature",
            b'{"schema":"nope","topic":"factory/robot-01/temperature","value":1,"timestamp":"t"}',
        )
        is False
    )
    assert ingest.rejected == 1
    assert ingest.handle_message(
        "factory/robot-01/temperature",
        b'{"schema":"twinops.mqtt.payload.v1","topic":"factory/robot-01/temperature",'
        b'"value":88.0,"timestamp":"2026-07-31T10:00:00Z","source":"plc"}',
    )
    assert ingest.received == 1
