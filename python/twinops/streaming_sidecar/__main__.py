"""python -m twinops.streaming_sidecar"""

from __future__ import annotations

import argparse

from twinops.streaming_sidecar.app import create_sidecar_app
from twinops.streaming_sidecar.config import SidecarConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinOps Kit streaming sidecar")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--idle-timeout", type=float, default=None)
    parser.add_argument(
        "--frame-source",
        choices=("mock", "kit", "kit-file"),
        default=None,
        help="mock | kit process | kit-file drop directory",
    )
    parser.add_argument(
        "--encoder",
        choices=("auto", "mock", "software", "nvenc"),
        default=None,
        help="media encoder selection (auto prefers nvenc→software→mock)",
    )
    parser.add_argument(
        "--kit-command",
        default=None,
        help="shell command to launch Kit when --frame-source kit",
    )
    parser.add_argument(
        "--kit-frame-dir",
        default=None,
        help="directory where Kit drops JPEG/PNG frames (kit-file)",
    )
    parser.add_argument(
        "--input-mirror",
        default=None,
        help="JSONL path mirroring browser input events for Kit",
    )
    args = parser.parse_args(argv)

    cfg = SidecarConfig.from_env()
    cfg = SidecarConfig(
        host=args.host or cfg.host,
        port=args.port if args.port is not None else cfg.port,
        idle_timeout_seconds=(
            args.idle_timeout
            if args.idle_timeout is not None
            else cfg.idle_timeout_seconds
        ),
        max_sessions=1,
        frame_source=args.frame_source or cfg.frame_source,
        encoder=args.encoder or cfg.encoder,
        kit_command=args.kit_command or cfg.kit_command,
        kit_frame_dir=args.kit_frame_dir or cfg.kit_frame_dir,
        input_mirror=args.input_mirror or cfg.input_mirror,
        twinops_api=cfg.twinops_api,
        gpu_index=cfg.gpu_index,
    )
    try:
        import uvicorn
    except ImportError:
        print("error: install live extras: pip install -e '.[live]'")
        return 2

    app = create_sidecar_app(cfg)
    print(f"TwinOps streaming sidecar on http://{cfg.host}:{cfg.port}")
    print(f"  frame-source: {cfg.frame_source}")
    print(f"  encoder:      {cfg.encoder}")
    print(f"  idle-timeout: {cfg.idle_timeout_seconds}s")
    print(f"  health: http://{cfg.host}:{cfg.port}/health")
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
