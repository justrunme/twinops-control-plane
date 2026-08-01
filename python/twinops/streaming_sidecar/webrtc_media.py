"""WebRTC media path — real PeerConnection when aiortc is installed."""

from __future__ import annotations

import asyncio
import fractions
import logging
from typing import Any

from twinops.streaming_sidecar.encoder import EncoderCapability, aiortc_available
from twinops.streaming_sidecar.frames import FrameSource
from twinops.streaming_sidecar.input_bridge import KitInputBridge
from twinops.streaming_sidecar.stats import StreamStats

logger = logging.getLogger(__name__)


def lab_echo_answer(offer: dict[str, Any], *, capability: EncoderCapability) -> dict[str, Any]:
    return {
        "type": "answer",
        "sdp": offer.get("sdp", ""),
        "labEcho": True,
        "provider": "twinops-kit-sidecar",
        "encoder": capability.backend,
        "mediaPath": "lab-echo",
        "note": (
            "Lab-echo SDP — browser keeps local MediaStream. "
            "Install twinops[streaming] (aiortc) for a real sidecar video track."
        ),
    }


class WebRTCMediaSession:
    """Owns at most one RTCPeerConnection for the single streaming session."""

    def __init__(
        self,
        *,
        frame_source: FrameSource,
        capability: EncoderCapability,
        input_bridge: KitInputBridge,
        stats: StreamStats,
    ) -> None:
        self.frame_source = frame_source
        self.capability = capability
        self.input_bridge = input_bridge
        self.stats = stats
        self._pc: Any | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def active(self) -> bool:
        return self._pc is not None

    async def answer_offer(self, offer: dict[str, Any]) -> dict[str, Any]:
        if not aiortc_available() or self.capability.backend == "mock":
            answer = lab_echo_answer(offer, capability=self.capability)
            self.stats.mark_media_ready()
            return answer
        return await self._answer_with_aiortc(offer)

    async def _answer_with_aiortc(self, offer: dict[str, Any]) -> dict[str, Any]:
        from aiortc import RTCPeerConnection, RTCSessionDescription
        from aiortc.mediastreams import VideoStreamTrack

        await self.close()
        pc = RTCPeerConnection()
        self._pc = pc
        self._loop = asyncio.get_running_loop()
        source = self.frame_source
        stats = self.stats
        bridge = self.input_bridge

        class TwinOpsVideoTrack(VideoStreamTrack):
            kind = "video"

            def __init__(self) -> None:
                super().__init__()
                self._count = 0

            async def recv(self) -> Any:  # type: ignore[override]
                pts, time_base = await self.next_timestamp()
                tick = source.tick()
                width = int(tick.get("width") or getattr(source, "width", 640) or 640)
                height = int(tick.get("height") or getattr(source, "height", 360) or 360)
                frame = _frame_from_tick(tick, width=width, height=height, count=self._count)
                frame.pts = pts
                frame.time_base = time_base or fractions.Fraction(1, 90000)
                self._count += 1
                stats.record_frame(bytes_estimate=width * height * 3)
                return frame

        pc.addTrack(TwinOpsVideoTrack())

        @pc.on("datachannel")
        def on_datachannel(channel: Any) -> None:
            @channel.on("message")
            def on_message(message: Any) -> None:
                try:
                    import json

                    payload = json.loads(message) if isinstance(message, str) else message
                    if isinstance(payload, dict):
                        bridge.push(payload)
                except Exception:  # noqa: BLE001
                    logger.debug("ignored input channel message", exc_info=True)

        @pc.on("connectionstatechange")
        async def on_state_change() -> None:
            state = pc.connectionState
            if state in {"failed", "closed", "disconnected"}:
                stats.record_disconnect()

        remote = RTCSessionDescription(
            sdp=str(offer.get("sdp") or ""),
            type=str(offer.get("type") or "offer"),
        )
        await pc.setRemoteDescription(remote)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        stats.mark_media_ready()
        assert pc.localDescription is not None
        return {
            "type": pc.localDescription.type,
            "sdp": pc.localDescription.sdp,
            "labEcho": False,
            "provider": "twinops-kit-sidecar",
            "encoder": self.capability.backend,
            "mediaPath": "webrtc-track",
            "note": (
                f"Real WebRTC video track from sidecar ({self.capability.backend}). "
                "Send mouse/keyboard JSON on a datachannel named 'twinops-input'."
            ),
        }

    async def close(self) -> None:
        pc = self._pc
        self._pc = None
        if pc is not None:
            try:
                await pc.close()
            except Exception:  # noqa: BLE001
                logger.debug("peer close failed", exc_info=True)


def _frame_from_tick(
    tick: dict[str, Any],
    *,
    width: int,
    height: int,
    count: int,
) -> Any:
    """Build an av.VideoFrame from a Kit drop path or synthetic RGB pulse."""
    from av import VideoFrame

    path = tick.get("path")
    if isinstance(path, str) and path:
        decoded = _decode_image_path(path)
        if decoded is not None:
            return decoded

    pixel = tick.get("pixel") or [40, 40, 40]
    r, g, b = (int(pixel[0]) % 256, int(pixel[1]) % 256, int(pixel[2]) % 256)
    try:
        import numpy as np

        arr = np.zeros((height, width, 3), dtype=np.uint8)
        shade = (count * 3) % 256
        arr[:, :, 0] = (r + shade) % 256
        arr[:, :, 1] = g
        arr[:, :, 2] = b
        return VideoFrame.from_ndarray(arr, format="rgb24")
    except Exception:  # noqa: BLE001 - keep media path alive
        frame = VideoFrame(width=width, height=height, format="yuv420p")
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        return frame


def _decode_image_path(path: str) -> Any | None:
    try:
        import av
    except ImportError:
        return None
    try:
        container = av.open(path)
        try:
            for frame in container.decode(video=0):
                return frame.reformat(format="rgb24")
        finally:
            container.close()
    except Exception:  # noqa: BLE001
        logger.debug("kit frame decode failed for %s", path, exc_info=True)
        return None
