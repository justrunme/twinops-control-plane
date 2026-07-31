"""Tests for MQTT topic catalog."""

from __future__ import annotations

from twinops.telemetry.topics import assembly_line_topics, topic_catalog


def test_topic_catalog_matches_bindings() -> None:
    catalog = topic_catalog()
    topics = assembly_line_topics()
    assert catalog["kind"] == "MqttTopicCatalog"
    assert len(catalog["spec"]["bindings"]) == len(topics)
    assert topics[0] == "factory/robot-01/temperature"
