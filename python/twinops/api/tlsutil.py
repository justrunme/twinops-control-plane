"""TLS / mTLS helpers for twinopsctl serve."""

from __future__ import annotations

import ssl
from pathlib import Path


def build_ssl_context(
    *,
    certfile: str | Path,
    keyfile: str | Path,
    client_ca: str | Path | None = None,
    require_client_cert: bool = False,
) -> ssl.SSLContext:
    """Build an SSLContext for uvicorn HTTPS, optionally requiring client certs."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(certfile), str(keyfile))
    if client_ca:
        ctx.load_verify_locations(cafile=str(client_ca))
        ctx.verify_mode = (
            ssl.CERT_REQUIRED if require_client_cert else ssl.CERT_OPTIONAL
        )
    return ctx
