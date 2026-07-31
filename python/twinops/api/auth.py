"""Optional bearer-token auth for the TwinOps live API (demo control plane)."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Unauthenticated probes stay open so compose/k8s readiness keeps working.
PUBLIC_PATHS = frozenset(
    {
        "/api/health",
        "/api/ready",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


def resolve_api_token(explicit: str | None = None) -> str | None:
    """Return the configured API token, or None when auth is disabled."""
    if explicit is not None:
        value = explicit.strip()
        return value or None
    env = (os.environ.get("TWINOPS_API_TOKEN") or "").strip()
    return env or None


def extract_bearer_token(authorization: str | None, header_token: str | None) -> str | None:
    if header_token and header_token.strip():
        return header_token.strip()
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1].strip()
        return token or None
    return None


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/assets"):
        return True
    # SPA shell + non-API routes (API/WS still gated).
    if not path.startswith("/api/") and not path.startswith("/ws/"):
        return True
    return False


def authorize_headers(
    *,
    authorization: str | None,
    header_token: str | None,
    expected: str,
) -> bool:
    provided = extract_bearer_token(authorization, header_token)
    return provided == expected


def build_http_auth_middleware(
    token: str,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if is_public_path(path):
            return await call_next(request)
        if authorize_headers(
            authorization=request.headers.get("authorization"),
            header_token=request.headers.get("x-twinops-token"),
            expected=token,
        ):
            return await call_next(request)
        return JSONResponse(
            status_code=401,
            content={
                "detail": "unauthorized",
                "hint": "Pass Authorization: Bearer <token> or X-TwinOps-Token",
            },
        )

    return middleware
