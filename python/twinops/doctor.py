"""Environment diagnostics for TwinOps demos."""

from __future__ import annotations

import importlib.util
import json
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "required": self.required,
        }


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _cmd_version(cmd: str) -> str | None:
    path = shutil.which(cmd)
    if not path:
        return None
    args = {
        "kubectl": [cmd, "version", "--client", "--output=yaml"],
        "docker": [cmd, "--version"],
    }.get(cmd, [cmd, "--version"])
    try:
        proc = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return path
    text = (proc.stdout or proc.stderr or "").strip().splitlines()
    if cmd == "kubectl":
        for line in text:
            if "gitVersion" in line:
                return line.strip()
    return text[0] if text else path


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def run_doctor(*, mqtt_host: str = "127.0.0.1", mqtt_port: int = 1883) -> list[Check]:
    checks: list[Check] = []

    twinopsctl = shutil.which("twinopsctl")
    checks.append(
        Check(
            name="twinopsctl",
            ok=twinopsctl is not None,
            detail=twinopsctl or "not on PATH (use make install / .venv)",
            required=True,
        )
    )

    for mod, required in (("yaml", True), ("fastapi", False), ("paho.mqtt", False)):
        ok = _has_module(mod)
        checks.append(
            Check(
                name=f"python:{mod}",
                ok=ok,
                detail="available" if ok else "missing",
                required=required,
            )
        )

    docker = _cmd_version("docker")
    checks.append(
        Check(
            name="docker",
            ok=docker is not None,
            detail=docker or "not installed (needed for mqtt-smoke / operator-demo)",
            required=False,
        )
    )

    for cmd in ("k3d", "kind", "kubectl"):
        ver = _cmd_version(cmd)
        checks.append(
            Check(
                name=cmd,
                ok=ver is not None,
                detail=ver or "not installed",
                required=False,
            )
        )

    mqtt_up = _port_open(mqtt_host, mqtt_port)
    checks.append(
        Check(
            name="mqtt-broker",
            ok=mqtt_up,
            detail=(
                f"{mqtt_host}:{mqtt_port} open"
                if mqtt_up
                else f"{mqtt_host}:{mqtt_port} closed (start deploy/demo/docker-compose.mqtt.yml)"
            ),
            required=False,
        )
    )

    catalog_path = Path("examples/assembly-line/mqtt-topics.json")
    try:
        from twinops.telemetry.topics import topic_catalog

        expected = topic_catalog()
        expected.pop("status", None)
        if catalog_path.is_file():
            current = json.loads(catalog_path.read_text(encoding="utf-8"))
            synced = current == expected
            checks.append(
                Check(
                    name="mqtt-topic-catalog",
                    ok=synced,
                    detail=(
                        "examples/assembly-line/mqtt-topics.json matches in-code catalog"
                        if synced
                        else "out of sync (run: python scripts/sync_mqtt_topics.py)"
                    ),
                    required=False,
                )
            )
        else:
            checks.append(
                Check(
                    name="mqtt-topic-catalog",
                    ok=False,
                    detail=f"missing {catalog_path}",
                    required=False,
                )
            )
    except Exception as exc:  # noqa: BLE001 - doctor must not crash
        checks.append(
            Check(
                name="mqtt-topic-catalog",
                ok=False,
                detail=f"catalog check failed: {exc}",
                required=False,
            )
        )

    acl_conf = Path("deploy/demo/mosquitto.acl.conf")
    checks.append(
        Check(
            name="mqtt-acl-profile",
            ok=acl_conf.is_file(),
            detail=(
                "deploy/demo/mosquitto.acl.conf present (optional ACL demo)"
                if acl_conf.is_file()
                else "missing deploy/demo/mosquitto.acl.conf"
            ),
            required=False,
        )
    )
    umbrella = Path("deploy/helm/twinops/Chart.yaml")
    checks.append(
        Check(
            name="helm-umbrella",
            ok=umbrella.is_file(),
            detail=(
                "deploy/helm/twinops umbrella chart present"
                if umbrella.is_file()
                else "missing deploy/helm/twinops"
            ),
            required=False,
        )
    )
    chart_lock = Path("deploy/helm/twinops/Chart.lock")
    checks.append(
        Check(
            name="helm-chartlock",
            ok=chart_lock.is_file(),
            detail=(
                "deploy/helm/twinops/Chart.lock present"
                if chart_lock.is_file()
                else "missing Chart.lock (run make helm-deps)"
            ),
            required=False,
        )
    )
    mqtt_tls = Path("deploy/demo/docker-compose.mqtt-tls.yml")
    checks.append(
        Check(
            name="mqtt-tls-profile",
            ok=mqtt_tls.is_file(),
            detail=(
                "deploy/demo/docker-compose.mqtt-tls.yml present (lab TLS stub)"
                if mqtt_tls.is_file()
                else "missing deploy/demo/docker-compose.mqtt-tls.yml"
            ),
            required=False,
        )
    )
    demo_gitops = Path("scripts/demo_gitops.sh")
    checks.append(
        Check(
            name="demo-gitops-script",
            ok=demo_gitops.is_file(),
            detail=(
                "scripts/demo_gitops.sh present"
                if demo_gitops.is_file()
                else "missing scripts/demo_gitops.sh"
            ),
            required=False,
        )
    )

    return checks
