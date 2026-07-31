"""Tests for twinopsctl completion."""

from __future__ import annotations

from twinops.cli import main


def test_completion_bash(capsys) -> None:
    try:
        main(["completion", "bash"])
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert "complete -F _twinopsctl_completions twinopsctl" in out
    assert "build" in out


def test_completion_zsh(capsys) -> None:
    try:
        main(["completion", "zsh"])
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert "compdef _twinopsctl_completions twinopsctl" in out
    assert "build" in out
