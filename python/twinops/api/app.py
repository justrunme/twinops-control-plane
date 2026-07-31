"""FastAPI application exposing live twin drift over HTTP + WebSocket."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from twinops import __version__
from twinops.api.live import LiveDriftRuntime
from twinops.api.store import TwinStore


class _WsClient:
    def __init__(self, websocket: WebSocket, loop: asyncio.AbstractEventLoop) -> None:
        self.websocket = websocket
        self.loop = loop

    def send_json(self, message: dict[str, Any]) -> None:
        future = asyncio.run_coroutine_threadsafe(
            self.websocket.send_json(message), self.loop
        )
        future.result(timeout=2)


def create_app(
    *,
    example_dir: str | Path,
    work_dir: str | Path,
    interval_seconds: float = 1.0,
    mqtt_host: str | None = None,
    mqtt_port: int = 1883,
    autostart: bool = True,
) -> FastAPI:
    store = TwinStore()
    runtime = LiveDriftRuntime(
        example_dir=Path(example_dir),
        work_dir=Path(work_dir),
        store=store,
        interval_seconds=interval_seconds,
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        runtime.bootstrap()
        if autostart:
            runtime.start()
        try:
            yield
        finally:
            runtime.stop()

    app = FastAPI(
        title="TwinOps Live API",
        version=__version__,
        description="Live telemetry + drift control plane for TwinOps demos",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.store = store
    app.state.runtime = runtime

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "service": "twinops-live"}

    @app.get("/api/twin")
    def twin() -> dict[str, Any]:
        return store.snapshot()

    @app.get("/api/drift/latest")
    def drift_latest() -> dict[str, Any]:
        return store.latest_drift or {}

    @app.get("/api/timeline")
    def timeline(limit: int = 50) -> dict[str, Any]:
        return {"items": store.timeline(limit=limit)}

    @app.post("/api/simulate/spike")
    def simulate_spike() -> dict[str, Any]:
        return runtime.trigger_spike()

    @app.post("/api/drift/refresh")
    def drift_refresh() -> dict[str, Any]:
        return runtime.evaluate_drift(record_telemetry=True)

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await websocket.accept()
        client = _WsClient(websocket, asyncio.get_running_loop())
        runtime.register_ws(client)
        try:
            await websocket.send_json({"type": "snapshot", "snapshot": store.snapshot()})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            runtime.unregister_ws(client)
        finally:
            runtime.unregister_ws(client)

    return app
