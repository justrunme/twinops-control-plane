"""WebRTC media path — aiortc PeerConnection with software or NVENC ingest bridge.

Honest encoder reporting:
- ``ingestEncoder`` — how pixels enter the sidecar (none / software / h264_nvenc)
- ``webrtcEncoder`` — what actually produces RTP (none / aiortc)
- ``mediaPath`` — lab-echo | webrtc-software | nvenc-mpegts-aiortc

NVENC today is an ffmpeg ingest bridge (encode → MPEG-TS → MediaPlayer decode),
not an end-to-end NVENC RTP encoder.
"""

from __future__ import annotations

import asyncio
import fractions
import logging
from pathlib import Path
from typing import Any

from twinops.streaming_sidecar.encoder import EncoderCapability, aiortc_available
from twinops.streaming_sidecar.frames import FrameSource
from twinops.streaming_sidecar.input_bridge import KitInputBridge
from twinops.streaming_sidecar.nvenc_bridge import NVENCBridge
from twinops.streaming_sidecar.stats import StreamStats

logger = logging.getLogger(__name__)


def lab_echo_answer(offer: dict[str, Any], *, capability: EncoderCapability) -> dict[str, Any]:
    return {
        "type": "answer",
        "sdp": offer.get("sdp", ""),
        "labEcho": True,
        "provider": "twinops-kit-sidecar",
        "encoder": capability.backend,
        "ingestEncoder": "none",
        "webrtcEncoder": "none",
        # Deprecated alias — do not treat as the RTP codec.
        "encoderInUse": "none",
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
        kit_frame_dir: str | Path | None = None,
        gpu_index: int = 0,
    ) -> None:
        self.frame_source = frame_source
        self.capability = capability
        self.input_bridge = input_bridge
        self.stats = stats
        self.kit_frame_dir = Path(kit_frame_dir) if kit_frame_dir else None
        self.gpu_index = gpu_index
        self._pc: Any | None = None
        self._player: Any | None = None
        self._nvenc: NVENCBridge | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.ingest_encoder: str = "none"
        self.webrtc_encoder: str = "none"
        self.media_path: str = "idle"

    @property
    def active(self) -> bool:
        return self._pc is not None

    @property
    def encoder_in_use(self) -> str:
        """Deprecated alias kept for older clients — prefer ingest/webrtc fields."""
        if self.media_path == "nvenc-mpegts-aiortc":
            return "nvenc-mpegts-aiortc"
        return self.webrtc_encoder if self.webrtc_encoder != "none" else self.ingest_encoder

    def media_report(self) -> dict[str, Any]:
        return {
            "ingestEncoder": self.ingest_encoder,
            "webrtcEncoder": self.webrtc_encoder,
            "encoderInUse": self.encoder_in_use,
            "mediaPath": self.media_path,
        }

    async def answer_offer(self, offer: dict[str, Any]) -> dict[str, Any]:
        if not aiortc_available() or self.capability.backend == "mock":
            answer = lab_echo_answer(offer, capability=self.capability)
            self.ingest_encoder = "none"
            self.webrtc_encoder = "none"
            self.media_path = "lab-echo"
            self.stats.mark_media_ready()
            return answer
        if self.capability.backend == "nvenc" and self.capability.nvenc:
            try:
                return await self._answer_with_nvenc(offer)
            except Exception as exc:  # noqa: BLE001 - fall back to software track
                logger.warning("NVENC bridge failed, falling back to software: %s", exc)
        return await self._answer_with_software(offer)

    async def _answer_with_nvenc(self, offer: dict[str, Any]) -> dict[str, Any]:
        from aiortc import RTCPeerConnection
        from aiortc.contrib.media import MediaPlayer

        await self.close()
        frame_dir = self.kit_frame_dir
        if frame_dir is None and getattr(self.frame_source, "directory", None):
            frame_dir = Path(self.frame_source.directory)  # type: ignore[attr-defined]
        bridge = NVENCBridge(frame_dir=frame_dir, gpu_index=self.gpu_index)
        url = await asyncio.to_thread(bridge.start)
        self._nvenc = bridge
        player = MediaPlayer(url, format="mpegts")
        self._player = player
        if player.video is None:
            bridge.stop()
            self._nvenc = None
            raise RuntimeError("MediaPlayer produced no video track from NVENC MPEG-TS")

        pc = RTCPeerConnection()
        self._pc = pc
        self._loop = asyncio.get_running_loop()
        pc.addTrack(player.video)
        self._wire_input_and_state(pc)
        answer = await self._complete_sdp(pc, offer)
        self.ingest_encoder = "h264_nvenc"
        self.webrtc_encoder = "aiortc"
        self.media_path = "nvenc-mpegts-aiortc"
        self.stats.mark_media_ready()
        return {
            **answer,
            "labEcho": False,
            "provider": "twinops-kit-sidecar",
            "encoder": self.capability.backend,
            **self.media_report(),
            "nvenc": bridge.status(),
            "note": (
                "NVENC ingest bridge: ffmpeg h264_nvenc → MPEG-TS → aiortc MediaPlayer "
                "decode → aiortc re-encodes RTP. Not end-to-end NVENC WebRTC."
            ),
        }

    async def _answer_with_software(self, offer: dict[str, Any]) -> dict[str, Any]:
        from aiortc import RTCPeerConnection
        from aiortc.mediastreams import VideoStreamTrack

        await self.close()
        pc = RTCPeerConnection()
        self._pc = pc
        self._loop = asyncio.get_running_loop()
        source = self.frame_source
        stats = self.stats

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
        self._wire_input_and_state(pc)
        answer = await self._complete_sdp(pc, offer)
        self.ingest_encoder = "software"
        self.webrtc_encoder = "aiortc"
        self.media_path = "webrtc-software"
        self.stats.mark_media_ready()
        return {
            **answer,
            "labEcho": False,
            "provider": "twinops-kit-sidecar",
            "encoder": self.capability.backend,
            **self.media_report(),
            "note": (
                "Real WebRTC video track; RTP encoder is aiortc (software). "
                "NVENC path is an ingest bridge only (see mediaPath=nvenc-mpegts-aiortc)."
            ),
        }

    def _wire_input_and_state(self, pc: Any) -> None:
        bridge = self.input_bridge
        stats = self.stats

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

    async def _complete_sdp(self, pc: Any, offer: dict[str, Any]) -> dict[str, Any]:
        from aiortc import RTCSessionDescription

        remote = RTCSessionDescription(
            sdp=str(offer.get("sdp") or ""),
            type=str(offer.get("type") or "offer"),
        )
        await pc.setRemoteDescription(remote)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await _wait_ice_complete(pc)
        assert pc.localDescription is not None
        return {
            "type": pc.localDescription.type,
            "sdp": pc.localDescription.sdp,
        }

    async def close(self) -> None:
        pc = self._pc
        player = self._player
        nvenc = self._nvenc
        self._pc = None
        self._player = None
        self._nvenc = None
        self.ingest_encoder = "none"
        self.webrtc_encoder = "none"
        self.media_path = "idle"
        if pc is not None:
            try:
                await pc.close()
            except Exception:  # noqa: BLE001
                logger.debug("peer close failed", exc_info=True)
        if player is not None:
            for track in (getattr(player, "audio", None), getattr(player, "video", None)):
                if track is not None:
                    try:
                        track.stop()
                    except Exception:  # noqa: BLE001
                        pass
        if nvenc is not None:
            await asyncio.to_thread(nvenc.stop)


async def _wait_ice_complete(pc: Any, *, timeout: float = 5.0) -> None:
    if getattr(pc, "iceGatheringState", None) == "complete":
        return
    done = asyncio.Event()

    @pc.on("icegatheringstatechange")
    def _on_state() -> None:
        if pc.iceGatheringState == "complete":
            done.set()

    if pc.iceGatheringState == "complete":
        return
    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
    except TimeoutError:
        logger.debug("ICE gathering timeout — continuing with partial candidates")


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
