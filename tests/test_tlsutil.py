"""Tests for HTTPS/mTLS SSLContext helper."""

from __future__ import annotations

import os
import ssl
import subprocess
from pathlib import Path

from twinops.api.tlsutil import build_ssl_context


def test_build_ssl_context_with_client_ca(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "gen_live_tls_certs.sh"
    out = tmp_path / "certs"
    env = os.environ.copy()
    env["OUT"] = str(out)
    subprocess.run(["bash", str(script)], check=True, env=env, capture_output=True, text=True)
    ctx = build_ssl_context(
        certfile=out / "server.crt",
        keyfile=out / "server.key",
        client_ca=out / "ca.crt",
        require_client_cert=True,
    )
    assert ctx.verify_mode == ssl.CERT_REQUIRED
