"""Sidecar configuration from env / CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SidecarConfig:
    host: str = "127.0.0.1"
    port: int = 8091
    idle_timeout_seconds: float = 300.0
    max_sessions: int = 1
    frame_source: str = "mock"  # mock | kit
    kit_command: str | None = None
    twinops_api: str | None = None
    gpu_index: int = 0

    @classmethod
    def from_env(cls) -> SidecarConfig:
        return cls(
            host=os.environ.get("TWINOPS_SIDECAR_HOST", "127.0.0.1"),
            port=int(os.environ.get("TWINOPS_SIDECAR_PORT", "8091")),
            idle_timeout_seconds=float(
                os.environ.get("TWINOPS_SIDECAR_IDLE_TIMEOUT", "300")
            ),
            max_sessions=1,
            frame_source=(
                os.environ.get("TWINOPS_SIDECAR_FRAME_SOURCE", "mock").strip().lower()
            ),
            kit_command=os.environ.get("TWINOPS_KIT_COMMAND") or None,
            twinops_api=os.environ.get("TWINOPS_API_URL") or None,
            gpu_index=int(os.environ.get("TWINOPS_GPU_INDEX", "0")),
        )
