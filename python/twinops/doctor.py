"""Environment diagnostics for TwinOps demos."""

from __future__ import annotations

import importlib.util
import shutil
import socket
import subprocess
from dataclasses import dataclass
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

    return checks
