"""Tests for the GPU-free Kit highlight client stub."""

from __future__ import annotations

import json
from unittest.mock import patch

from twinops_highlight.client import TwinOpsHighlightClient


def test_fetch_streaming_session_uses_token() -> None:
    payload = {
        "metadata": {"mode": "mock"},
        "status": {"phase": "MockReady"},
        "spec": {"streamUrl": None},
    }

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=_Resp()) as mocked:
        client = TwinOpsHighlightClient("http://127.0.0.1:8080", token="secret")
        assert client.fetch_streaming_session()["metadata"]["mode"] == "mock"
        request = mocked.call_args[0][0]
        assert request.get_header("Authorization") == "Bearer secret"
