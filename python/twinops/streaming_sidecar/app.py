"""FastAPI app for the Kit streaming sidecar."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from twinops import __version__
from twinops.streaming_sidecar.config import SidecarConfig
from twinops.streaming_sidecar.frames import select_frame_source
from twinops.streaming_sidecar.metrics import gpu_metrics, prometheus_text
from twinops.streaming_sidecar.session import StreamingSessionManager


def create_sidecar_app(config: SidecarConfig | None = None) -> FastAPI:
    cfg = config or SidecarConfig.from_env()
    try:
        source = select_frame_source(
            cfg.frame_source,
            kit_command=cfg.kit_command,
            kit_frame_dir=cfg.kit_frame_dir,
        )
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    manager = StreamingSessionManager(
        frame_source=source,
        idle_timeout_seconds=cfg.idle_timeout_seconds,
        max_sessions=cfg.max_sessions,
        encoder=cfg.encoder,
        input_mirror=cfg.input_mirror,
        kit_frame_dir=cfg.kit_frame_dir,
        gpu_index=cfg.gpu_index,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        manager.start()
        try:
            yield
        finally:
            manager.stop()

    app = FastAPI(
        title="TwinOps Kit Streaming Sidecar",
        version=__version__,
        description=(
            "Single-session WebRTC path for Kit/mock frames with optional NVENC host. "
            "Not a multi-tenant NVCF cluster."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.manager = manager
    app.state.config = cfg

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "twinops-streaming-sidecar",
            "version": __version__,
            "shuttingDown": manager.shutting_down,
            "encoder": manager.capability.backend,
        }

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        ok = not manager.shutting_down
        return {
            "status": "ready" if ok else "not_ready",
            "frameSource": manager.frame_source.name,
            "encoder": manager.capability.to_dict(),
            "sessionActive": manager.active() is not None,
        }

    @app.get("/v1/status")
    def status() -> dict[str, Any]:
        payload = manager.status()
        payload["gpu"] = gpu_metrics(gpu_index=cfg.gpu_index)
        payload["twinopsApi"] = cfg.twinops_api
        payload["limitations"] = [
            "Single session / single GPU / single browser client",
            "No TURN cluster, autoscaling, multi-region, or NVCF",
            "Real WebRTC media requires pip install 'twinops[streaming]'",
            "Without aiortc the API falls back to lab-echo SDP (GPU-free demo still works)",
            "NVENC uses host ffmpeg h264_nvenc when present; otherwise software track",
        ]
        return payload

    @app.post("/v1/sessions")
    async def create_session(request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001 - empty body is fine
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        try:
            session = manager.create(client_id=str(payload.get("clientId") or ""))
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "session": session.to_dict()}

    @app.get("/v1/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        session = manager.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="unknown session")
        session.touch()
        return {"ok": True, "session": session.to_dict()}

    @app.delete("/v1/sessions/{session_id}")
    def delete_session(session_id: str) -> dict[str, Any]:
        if not manager.delete(session_id):
            raise HTTPException(status_code=404, detail="unknown session")
        return {"ok": True, "deleted": session_id}

    @app.post("/v1/sessions/{session_id}/signal")
    async def signal(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action") or "").strip().lower()
        try:
            if action == "offer":
                offer = payload.get("sdp") or payload.get("offer")
                if not isinstance(offer, dict):
                    raise HTTPException(status_code=400, detail="offer sdp required")
                answer = await manager.answer_offer(session_id, offer)
                return {"ok": True, "sessionId": session_id, "answer": answer}
            if action == "candidate":
                candidate = payload.get("candidate")
                if not isinstance(candidate, dict):
                    raise HTTPException(status_code=400, detail="candidate required")
                manager.add_candidate(
                    session_id, candidate, local=bool(payload.get("local"))
                )
                return {"ok": True, "sessionId": session_id}
            if action == "get":
                session = manager.get(session_id)
                if session is None:
                    raise HTTPException(status_code=404, detail="unknown session")
                return {"ok": True, **session.to_dict()}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=f"unknown action: {action}")

    @app.post("/v1/sessions/{session_id}/frame")
    def frame_tick(session_id: str) -> dict[str, Any]:
        try:
            return manager.tick_frames(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/sessions/{session_id}/input")
    def input_event(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return manager.push_input(session_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/metrics")
    def metrics() -> Response:
        session = manager.active()
        frames = 0
        stats = {}
        if session is not None:
            stats = session.stats.snapshot()
            frames = int(stats.get("frames") or 0)
        elif hasattr(manager.frame_source, "frames_emitted"):
            frames = int(manager.frame_source.frames_emitted)  # type: ignore[attr-defined]
        text = prometheus_text(
            gpu_metrics(gpu_index=cfg.gpu_index),
            sessions=1 if session else 0,
            frames=frames,
            stats=stats,
            encoder=manager.capability.backend,
        )
        return Response(content=text, media_type="text/plain; version=0.0.4")

    return app
