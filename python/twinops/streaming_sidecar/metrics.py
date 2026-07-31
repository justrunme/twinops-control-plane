"""GPU / process metrics for the streaming sidecar (DCGM when available)."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any


def gpu_metrics(*, gpu_index: int = 0) -> dict[str, Any]:
    """Best-effort GPU snapshot — nvidia-smi, else honest zeros."""
    if shutil.which("nvidia-smi") is None:
        return {
            "available": False,
            "source": "none",
            "gpuIndex": gpu_index,
            "utilizationPercent": 0,
            "memoryUsedMiB": 0,
            "memoryTotalMiB": 0,
            "temperatureC": 0,
            "note": "No nvidia-smi — mock/CI host without GPU",
        }
    query = (
        "index,utilization.gpu,memory.used,memory.total,temperature.gpu,name"
    )
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                f"--id={gpu_index}",
                f"--query-gpu={query}",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=3,
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "source": "nvidia-smi-error",
            "gpuIndex": gpu_index,
            "error": str(exc),
        }
    parts = [p.strip() for p in out.split(",")]
    if len(parts) < 5:
        return {
            "available": False,
            "source": "nvidia-smi-parse-error",
            "gpuIndex": gpu_index,
            "raw": out,
        }
    return {
        "available": True,
        "source": "nvidia-smi",
        "gpuIndex": int(parts[0]) if parts[0].isdigit() else gpu_index,
        "utilizationPercent": _num(parts[1]),
        "memoryUsedMiB": _num(parts[2]),
        "memoryTotalMiB": _num(parts[3]),
        "temperatureC": _num(parts[4]),
        "name": parts[5] if len(parts) > 5 else "",
        "dcgm": _dcgm_available(),
    }


def prometheus_text(metrics: dict[str, Any], *, sessions: int, frames: int) -> str:
    gpu_up = 1 if metrics.get("available") else 0
    lines = [
        "# HELP twinops_sidecar_gpu_available GPU metrics source available (1/0).",
        "# TYPE twinops_sidecar_gpu_available gauge",
        f"twinops_sidecar_gpu_available {gpu_up}",
        "# HELP twinops_sidecar_gpu_utilization_percent GPU utilization.",
        "# TYPE twinops_sidecar_gpu_utilization_percent gauge",
        f"twinops_sidecar_gpu_utilization_percent {float(metrics.get('utilizationPercent') or 0)}",
        "# HELP twinops_sidecar_gpu_memory_used_mib GPU memory used MiB.",
        "# TYPE twinops_sidecar_gpu_memory_used_mib gauge",
        f"twinops_sidecar_gpu_memory_used_mib {float(metrics.get('memoryUsedMiB') or 0)}",
        "# HELP twinops_sidecar_sessions Active streaming sessions.",
        "# TYPE twinops_sidecar_sessions gauge",
        f"twinops_sidecar_sessions {sessions}",
        "# HELP twinops_sidecar_frames_emitted_total Synthetic/Kit frames emitted.",
        "# TYPE twinops_sidecar_frames_emitted_total counter",
        f"twinops_sidecar_frames_emitted_total {frames}",
        "",
    ]
    return "\n".join(lines)


def _num(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def _dcgm_available() -> bool:
    return bool(os.environ.get("DCGM_HOST") or shutil.which("dcgmi"))
