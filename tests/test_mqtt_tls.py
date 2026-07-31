"""Tests for MQTT TLS helper configuration."""

from __future__ import annotations

import ssl

from twinops.telemetry.bus import configure_mqtt_tls


class _FakeClient:
    def __init__(self) -> None:
        self.tls_args: tuple | None = None
        self.insecure: bool | None = None

    def tls_set(self, *args, **kwargs) -> None:
        self.tls_args = (args, kwargs)

    def tls_insecure_set(self, value: bool) -> None:
        self.insecure = value


def test_configure_mqtt_tls_noop() -> None:
    client = _FakeClient()
    configure_mqtt_tls(client)
    assert client.tls_args is None


def test_configure_mqtt_tls_insecure() -> None:
    client = _FakeClient()
    configure_mqtt_tls(client, tls_insecure=True)
    assert client.tls_args is not None
    assert client.tls_args[1].get("cert_reqs") == ssl.CERT_NONE
    assert client.insecure is True


def test_configure_mqtt_tls_ca() -> None:
    client = _FakeClient()
    configure_mqtt_tls(client, ca_certs="/tmp/server.crt")
    assert client.tls_args == ((), {"ca_certs": "/tmp/server.crt"})
