"""Optional demo SSO via signed JWT (Bearer), alongside API token auth."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any


def resolve_sso_secret(explicit: str | None = None) -> str | None:
    if explicit is not None:
        value = explicit.strip()
        return value or None
    env = (os.environ.get("TWINOPS_SSO_JWT_SECRET") or "").strip()
    return env or None


def resolve_sso_audience() -> str | None:
    value = (os.environ.get("TWINOPS_SSO_AUDIENCE") or "twinops-live").strip()
    return value or None


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def issue_demo_jwt(
    *,
    secret: str,
    subject: str = "demo-user",
    audience: str | None = None,
    ttl_seconds: int = 3600,
) -> str:
    """Issue an HS256 JWT for local SSO demos (not an IdP)."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + ttl_seconds,
        "iss": "twinops-demo-sso",
    }
    aud = audience if audience is not None else resolve_sso_audience()
    if aud:
        payload["aud"] = aud
    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{segments[0]}.{segments[1]}.{_b64url_encode(sig)}"


def validate_hs256_jwt(
    token: str,
    *,
    secret: str,
    audience: str | None = None,
) -> dict[str, Any] | None:
    """Validate a compact HS256 JWT. Returns claims or None."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        return None
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        provided = _b64url_decode(sig_b64)
    except Exception:  # noqa: BLE001
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:  # noqa: BLE001
        return None
    if header.get("alg") != "HS256":
        return None
    now = int(time.time())
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < now:
        return None
    aud = audience if audience is not None else resolve_sso_audience()
    if aud:
        claim_aud = payload.get("aud")
        if isinstance(claim_aud, list):
            if aud not in claim_aud:
                return None
        elif claim_aud != aud:
            return None
    return payload
