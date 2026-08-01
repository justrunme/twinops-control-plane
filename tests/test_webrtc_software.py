"""Integration: real aiortc software PeerConnection with frame receive."""

from __future__ import annotations

import asyncio
from typing import Any

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


def test_software_webrtc_receives_frames() -> None:
    asyncio.run(_software_webrtc_receives_frames())


async def _software_webrtc_receives_frames() -> None:
    source = MockFrameSource(width=320, height=180, fps=15.0)
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
        received: list[Any] = []
        done = asyncio.Event()

        @pc.on("track")
        def on_track(track: Any) -> None:
            async def consume() -> None:
                try:
                    for _ in range(3):
                        frame = await asyncio.wait_for(track.recv(), timeout=5)
                        received.append(frame)
                finally:
                    done.set()

            asyncio.ensure_future(consume())

        pc.addTransceiver("video", direction="recvonly")
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        while pc.iceGatheringState != "complete":
            await asyncio.sleep(0.05)

        answer = await media.answer_offer(
            {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp}
        )
        assert answer.get("labEcho") is False
        assert answer.get("ingestEncoder") == "software"
        assert answer.get("webrtcEncoder") == "aiortc"
        assert answer.get("mediaPath") == "webrtc-software"
        await pc.setRemoteDescription(
            RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
        )
        await asyncio.wait_for(done.wait(), timeout=10)
        assert len(received) >= 1
        assert received[0] is not None
        snap = stats.snapshot()
        assert snap["startupTimeMs"] is not None
        assert snap["frames"] >= 1
        await pc.close()
    finally:
        await media.close()
        source.stop()
