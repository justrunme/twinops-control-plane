"""GPU / software encoder capability probe for the Kit streaming sidecar."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Literal

EncoderBackend = Literal["mock", "software", "nvenc"]


@dataclass(frozen=True)
class EncoderCapability:
    backend: EncoderBackend
    aiortc: bool
    nvidia_smi: bool
    ffmpeg: bool
    nvenc: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "aiortc": self.aiortc,
            "nvidiaSmi": self.nvidia_smi,
            "ffmpeg": self.ffmpeg,
            "nvenc": self.nvenc,
            "notes": list(self.notes),
            "realWebRtcMedia": self.aiortc and self.backend != "mock",
        }


def aiortc_available() -> bool:
    try:
        import aiortc  # noqa: F401
        import av  # noqa: F401

        return True
    except ImportError:
        return False


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def nvidia_smi_available() -> bool:
    return shutil.which("nvidia-smi") is not None


def nvenc_available() -> bool:
    if not (ffmpeg_available() and nvidia_smi_available()):
        return False
    try:
        out = subprocess.check_output(
            ["ffmpeg", "-hide_banner", "-encoders"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "h264_nvenc" in out


def probe_encoder(preferred: str = "auto") -> EncoderCapability:
    """Select encoder backend. ``auto`` prefers nvenc → software → mock."""
    preferred = (preferred or "auto").strip().lower()
    has_aiortc = aiortc_available()
    has_ffmpeg = ffmpeg_available()
    has_smi = nvidia_smi_available()
    has_nvenc = nvenc_available()
    notes: list[str] = []

    if preferred == "mock":
        backend: EncoderBackend = "mock"
        notes.append("Forced mock encoder — lab-echo SDP unless aiortc forced elsewhere")
    elif preferred == "nvenc":
        backend = "nvenc" if has_nvenc else "software"
        if not has_nvenc:
            notes.append("nvenc requested but unavailable — falling back to software")
    elif preferred == "software":
        backend = "software"
    else:  # auto
        if has_nvenc:
            backend = "nvenc"
        elif has_aiortc:
            backend = "software"
        else:
            backend = "mock"
            notes.append("No aiortc/av — install twinops[streaming] for real WebRTC media")

    if backend in {"software", "nvenc"} and not has_aiortc:
        notes.append(
            "Encoder selected but aiortc missing — signaling falls back to lab-echo "
            "until pip install 'twinops[streaming]'"
        )
    if backend == "nvenc":
        notes.append("NVENC available via ffmpeg h264_nvenc; WebRTC track uses aiortc + GPU host")
    return EncoderCapability(
        backend=backend,
        aiortc=has_aiortc,
        nvidia_smi=has_smi,
        ffmpeg=has_ffmpeg,
        nvenc=has_nvenc,
        notes=notes,
    )
