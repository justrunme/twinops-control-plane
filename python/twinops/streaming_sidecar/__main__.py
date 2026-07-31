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
        choices=("mock", "kit"),
        default=None,
        help="mock synthetic frames (default) or kit process supervisor",
    )
    parser.add_argument(
        "--kit-command",
        default=None,
        help="shell command to launch Kit when --frame-source kit",
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
        kit_command=args.kit_command or cfg.kit_command,
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
    print(f"  idle-timeout: {cfg.idle_timeout_seconds}s")
    print(f"  health: http://{cfg.host}:{cfg.port}/health")
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
