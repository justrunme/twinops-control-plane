#!/usr/bin/env bash
# NVENC ingest-bridge smoke: sidecar --encoder nvenc + client track.recv().
# Skips cleanly when h264_nvenc / nvidia-smi / aiortc are unavailable.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HOST="${TWINOPS_SIDECAR_HOST:-127.0.0.1}"
PORT="${TWINOPS_SIDECAR_PORT:-18092}"
BASE="http://${HOST}:${PORT}"
TWINOPSCTL="${TWINOPSCTL:-${ROOT}/.venv/bin/twinopsctl}"
PYTHON="${PYTHON:-${ROOT}/.venv/bin/python}"
LOG="${TMPDIR:-/tmp}/twinops-nvenc-smoke.log"
OUT="${TMPDIR:-/tmp}/twinops-nvenc-smoke"
FRAME_DIR="${TWINOPS_KIT_FRAME_DIR:-${OUT}/frames}"

mkdir -p "${OUT}" "${FRAME_DIR}"

if [[ ! -x "${TWINOPSCTL}" ]]; then
  make install
fi

OUT="${OUT}" "${PYTHON}" - <<'PY'
import json, os, sys
from pathlib import Path
from twinops.streaming_sidecar.encoder import probe_encoder, aiortc_available

out = Path(os.environ["OUT"])
out.mkdir(parents=True, exist_ok=True)
cap = probe_encoder("nvenc")
(out / "encoder.json").write_text(json.dumps(cap.to_dict(), indent=2))
if not aiortc_available():
    print("SKIP: twinops[streaming] (aiortc) not installed")
    sys.exit(2)
if not cap.nvenc:
    print("SKIP: h264_nvenc / nvidia-smi not available on host")
    sys.exit(2)
print("NVENC capability OK")
PY
rc=$?
if [[ "${rc}" -eq 2 ]]; then
  exit 0
fi
if [[ "${rc}" -ne 0 ]]; then
  exit "${rc}"
fi

"${TWINOPSCTL}" streaming-sidecar \
  --host "${HOST}" --port "${PORT}" \
  --idle-timeout 120 \
  --encoder nvenc \
  --frame-source kit-file \
  --kit-frame-dir "${FRAME_DIR}" \
  >"${LOG}" 2>&1 &
PID=$!

cleanup() {
  if kill -0 "${PID}" 2>/dev/null; then
    kill "${PID}" 2>/dev/null || true
    wait "${PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo -n "==> Waiting for sidecar health"
for _ in $(seq 1 40); do
  if curl -fsS "${BASE}/health" >/dev/null 2>&1; then
    echo " OK"
    break
  fi
  if ! kill -0 "${PID}" 2>/dev/null; then
    echo
    tail -n 60 "${LOG}" || true
    exit 1
  fi
  echo -n "."
  sleep 0.25
done

SID="$("${PYTHON}" - <<PY
import json, urllib.request
req = urllib.request.Request("${BASE}/v1/sessions", data=b'{"clientId":"nvenc-smoke"}',
                            headers={"content-type":"application/json"}, method="POST")
print(json.load(urllib.request.urlopen(req))["session"]["sessionId"])
PY
)"

"${PYTHON}" - <<PY
import asyncio, json, urllib.request
from aiortc import RTCPeerConnection, RTCSessionDescription

BASE = "${BASE}"
SID = "${SID}"

async def main() -> None:
    pc = RTCPeerConnection()
    frames = []
    done = asyncio.Event()

    @pc.on("track")
    def on_track(track):
        async def consume():
            try:
                for _ in range(3):
                    frames.append(await asyncio.wait_for(track.recv(), timeout=8))
            finally:
                done.set()
        asyncio.ensure_future(consume())

    pc.addTransceiver("video", direction="recvonly")
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    while pc.iceGatheringState != "complete":
        await asyncio.sleep(0.05)

    payload = json.dumps({
        "action": "offer",
        "sdp": {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp},
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/v1/sessions/{SID}/signal",
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    answer = json.load(urllib.request.urlopen(req))["answer"]
    report = {
        "ingestEncoder": answer.get("ingestEncoder"),
        "webrtcEncoder": answer.get("webrtcEncoder"),
        "mediaPath": answer.get("mediaPath"),
        "labEcho": answer.get("labEcho"),
    }
    open("${OUT}/answer.json", "w").write(json.dumps({**report, "note": answer.get("note")}, indent=2))
    assert answer.get("labEcho") is False, answer
    assert answer.get("ingestEncoder") == "h264_nvenc", answer
    assert answer.get("webrtcEncoder") == "aiortc", answer
    assert answer.get("mediaPath") == "nvenc-mpegts-aiortc", answer

    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
    await asyncio.wait_for(done.wait(), timeout=15)
    assert len(frames) >= 1, "no frames received"
    open("${OUT}/frames.txt", "w").write(f"received={len(frames)}\n")
    await pc.close()
    print("NVENC ingest-bridge smoke OK:", report, "frames=", len(frames))

asyncio.run(main())
PY

curl -fsS "${BASE}/v1/status" >"${OUT}/status.json"
curl -fsS "${BASE}/metrics" >"${OUT}/metrics.txt" || true
cp "${LOG}" "${OUT}/sidecar.log" || true
echo "artifacts: ${OUT}"
echo "streaming-nvenc-smoke OK"
