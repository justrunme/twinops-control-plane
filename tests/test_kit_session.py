"""Kit session-layer highlight state machine (no Omniverse required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extensions" / "twinops_highlight"
if str(EXT) not in sys.path:
    sys.path.insert(0, str(EXT))

from twinops_highlight.session import RuntimeState, SessionHighlightLayer  # noqa: E402


def test_session_apply_clear_and_idempotent() -> None:
    layer = SessionHighlightLayer()
    targets = [
        {
            "prim": "/World/Factory/LineA/Robot01",
            "color": [0.9, 0.1, 0.1],
            "intensity": 0.8,
            "status": "CRITICAL",
        }
    ]
    notes = layer.apply(targets)
    assert layer.state == RuntimeState.HIGHLIGHT_APPLIED
    assert "/World/Factory/LineA/Robot01" in layer.overrides
    assert any("SESSION SET" in note for note in notes)

    again = layer.apply(targets)
    assert any("idempotent" in note for note in again)

    layer.clear()
    assert layer.state == RuntimeState.HIGHLIGHT_CLEARED
    assert layer.overrides == {}
    assert layer.snapshot()["mutatesSource"] is False


def test_session_invalid_prim_and_reconnect() -> None:
    layer = SessionHighlightLayer()
    layer.apply(
        [{"prim": "/Missing", "color": [1, 0, 0], "intensity": 1, "status": "DRIFT"}],
        valid_prims={"/World/Robot"},
    )
    assert layer.state == RuntimeState.INVALID_PRIM

    layer.apply(
        [
            {
                "prim": "/World/Robot",
                "color": [1, 0, 0],
                "intensity": 1,
                "status": "DRIFT",
            }
        ],
        valid_prims={"/World/Robot"},
    )
    notes = layer.restore_after_reconnect()
    assert layer.state == RuntimeState.HIGHLIGHT_APPLIED
    assert any("reconnect restore" in note for note in notes)


def test_session_invalid_payload() -> None:
    layer = SessionHighlightLayer()
    layer.apply("not-a-list")  # type: ignore[arg-type]
    assert layer.state == RuntimeState.INVALID_PAYLOAD
