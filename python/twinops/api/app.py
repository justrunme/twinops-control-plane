"""FastAPI application exposing live twin drift over HTTP + WebSocket."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from twinops import __version__
from twinops.api.auth import authorize_headers, build_http_auth_middleware, resolve_api_token
from twinops.api.live import LiveDriftRuntime
from twinops.api.store import TwinStore
from twinops.api.streaming import mock_streaming_session


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
    mqtt_ingest: bool = True,
    autostart: bool = True,
    web_dist: str | Path | None = None,
    api_token: str | None = None,
) -> FastAPI:
    store = TwinStore()
    runtime = LiveDriftRuntime(
        example_dir=Path(example_dir),
        work_dir=Path(work_dir),
        store=store,
        interval_seconds=interval_seconds,
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_ingest=mqtt_ingest,
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
    token = resolve_api_token(api_token)
    if token:
        app.middleware("http")(build_http_auth_middleware(token))
    app.state.store = store
    app.state.runtime = runtime
    app.state.api_token_configured = bool(token)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "service": "twinops-live",
            "mqtt": runtime.mqtt_status(),
            "auth": {"required": bool(token)},
        }

    @app.get("/api/ready")
    def ready() -> dict[str, Any]:
        """Readiness: twin metadata loaded and at least one drift evaluation present."""
        twin_name = (runtime.store.twin_meta or {}).get("name")
        has_drift_report = runtime.store.latest_drift is not None
        ok = bool(twin_name) and has_drift_report
        return {
            "status": "ready" if ok else "not_ready",
            "version": __version__,
            "twin": twin_name,
            "hasDriftReport": has_drift_report,
        }

    @app.get("/api/twin")
    def twin() -> dict[str, Any]:
        return store.snapshot()

    @app.get("/api/drift/latest")
    def drift_latest() -> dict[str, Any]:
        return store.latest_drift or {}

    @app.get("/api/drift/report", response_class=HTMLResponse)
    def drift_report() -> HTMLResponse:
        """Self-contained HTML drift dashboard from the latest evaluation."""
        return HTMLResponse(runtime.drift_html())

    @app.get("/api/drift/csv")
    def drift_csv() -> PlainTextResponse:
        """CSV export of the latest drift findings."""
        return PlainTextResponse(
            runtime.drift_csv(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="drift-report.csv"'},
        )

    @app.get("/api/scene")
    def scene() -> dict[str, Any]:
        """OpenUSD prim highlight snapshot (Omniverse-ready, GPU not required)."""
        return runtime.scene_snapshot()

    @app.get("/api/scene/report", response_class=HTMLResponse)
    def scene_report() -> HTMLResponse:
        """Self-contained HTML scene highlight dashboard from the latest snapshot."""
        return HTMLResponse(runtime.scene_html())

    @app.get("/api/mqtt/topics")
    def mqtt_topics() -> dict[str, Any]:
        """Canonical demo MQTT topic catalog (+ live ingest status when enabled)."""
        from twinops.telemetry.topics import topic_catalog

        catalog = topic_catalog()
        mqtt = runtime.mqtt_status()
        catalog["status"] = {
            "mqtt": mqtt,
        }
        return catalog

    @app.get("/api/metrics")
    def metrics() -> dict[str, Any]:
        """Compact control-plane metrics for demos / scrape adapters."""
        return runtime.metrics()

    @app.get("/metrics")
    def metrics_prometheus() -> Any:
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(
            runtime.metrics_prometheus(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/api/timeline")
    def timeline(limit: int = 50) -> dict[str, Any]:
        return {"items": store.timeline(limit=limit)}

    @app.post("/api/simulate/spike")
    def simulate_spike() -> dict[str, Any]:
        return runtime.trigger_spike()

    @app.post("/api/reconcile")
    def reconcile() -> dict[str, Any]:
        return runtime.reconcile()

    @app.get("/api/proposal/latest")
    def proposal_latest() -> dict[str, Any]:
        return store.latest_proposal or {}

    @app.get("/api/streaming/session")
    def streaming_session(request: Request) -> dict[str, Any]:
        """Mock Kit App Streaming session descriptor (GPU-free placeholder)."""
        base = str(request.base_url).rstrip("/")
        return mock_streaming_session(base_url=base)

    @app.post("/api/drift/refresh")
    def drift_refresh() -> dict[str, Any]:
        return runtime.evaluate_drift(record_telemetry=True)

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        if token and not authorize_headers(
            authorization=websocket.headers.get("authorization"),
            header_token=websocket.headers.get("x-twinops-token"),
            expected=token,
        ):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        client = _WsClient(websocket, asyncio.get_running_loop())
        runtime.register_ws(client)
        try:
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "snapshot": store.snapshot(),
                    "scene": runtime.scene_snapshot(),
                }
            )
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            runtime.unregister_ws(client)
        finally:
            runtime.unregister_ws(client)

    dist = Path(web_dist).resolve() if web_dist else None
    if dist and dist.is_dir() and (dist / "index.html").is_file():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(dist / "index.html")

        @app.get("/{path:path}")
        def spa_fallback(path: str) -> FileResponse:
            candidate = dist / path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app
