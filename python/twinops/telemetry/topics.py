"""Canonical MQTT topic catalog for the assembly-line demo."""

from __future__ import annotations

from typing import Any

from twinops.telemetry.ingest import TopicBinding

# Topic → OpenUSD prim / twinops attribute bindings used by publish + ingest.
ASSEMBLY_LINE_TOPIC_BINDINGS: tuple[TopicBinding, ...] = (
    TopicBinding(
        topic="factory/robot-01/temperature",
        prim="/World/Factory/LineA/Robot01",
        attribute="twinops:temperature",
    ),
    TopicBinding(
        topic="factory/robot-01/status",
        prim="/World/Factory/LineA/Robot01",
        attribute="twinops:status",
    ),
    TopicBinding(
        topic="factory/robot-01/firmware",
        prim="/World/Factory/LineA/Robot01",
        attribute="twinops:firmware",
    ),
    TopicBinding(
        topic="factory/conveyor-01/speed",
        prim="/World/Factory/LineA/Conveyor01",
        attribute="twinops:speed",
    ),
    TopicBinding(
        topic="factory/conveyor-01/status",
        prim="/World/Factory/LineA/Conveyor01",
        attribute="twinops:status",
    ),
    TopicBinding(
        topic="factory/scanner-01/status",
        prim="/World/Factory/LineA/Scanner01",
        attribute="twinops:status",
    ),
)


def assembly_line_topics() -> list[str]:
    return [item.topic for item in ASSEMBLY_LINE_TOPIC_BINDINGS]


def topic_catalog() -> dict[str, Any]:
    """JSON-serializable catalog for docs / GET /api/mqtt/topics."""
    return {
        "apiVersion": "twinops.io/v1alpha1",
        "kind": "MqttTopicCatalog",
        "metadata": {
            "name": "assembly-line",
            "description": "Demo MQTT topics for TwinOps live + mqtt-smoke",
        },
        "spec": {
            "ignoreSources": ["twinops", "twinops-bus", "twinops-simulator"],
            "bindings": [
                {
                    "topic": item.topic,
                    "prim": item.prim,
                    "attribute": item.attribute,
                }
                for item in ASSEMBLY_LINE_TOPIC_BINDINGS
            ],
        },
    }
