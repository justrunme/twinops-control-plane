"""Integration: real aiortc software PeerConnection (no GPU required)."""

from __future__ import annotations

import asyncio

import pytest
from twinops.streaming_sidecar.encoder import aiortc_available, probe_encoder
from twinops.streaming_sidecar.frames import MockFrameSource
from twinops.streaming_sidecar.input_bridge import KitInputBridge
from twinops.streaming_sidecar.stats import StreamStats
from twinops.streaming_sidecar.webrtc_media import WebRTCMediaSession

pytestmark = pytest.mark.skipif(
    not aiortc_available(),
    reason="twinops[streaming] (aiortc/av) not installed",
)


def test_software_webrtc_answer_not_lab_echo() -> None:
    asyncio.run(_software_webrtc_answer_not_lab_echo())


async def _software_webrtc_answer_not_lab_echo() -> None:
    source = MockFrameSource()
    source.start()
    stats = StreamStats()
    media = WebRTCMediaSession(
        frame_source=source,
        capability=probe_encoder("software"),
        input_bridge=KitInputBridge(),
        stats=stats,
    )
    try:
        from aiortc import RTCPeerConnection, RTCSessionDescription

        pc = RTCPeerConnection()
        pc.addTransceiver("video", direction="recvonly")
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        answer = await media.answer_offer(
            {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp}
        )
        assert answer.get("labEcho") is False
        assert answer.get("encoderInUse") == "software"
        assert answer.get("mediaPath") == "webrtc-software"
        assert "sdp" in answer and len(answer["sdp"]) > 20
        await pc.setRemoteDescription(
            RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
        )
        await asyncio.sleep(0.5)
        snap = stats.snapshot()
        assert snap["startupTimeMs"] is not None
        await pc.close()
    finally:
        await media.close()
        source.stop()
