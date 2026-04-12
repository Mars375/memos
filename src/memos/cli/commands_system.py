"""MemOS CLI — system commands (serve, mcp, config)."""

from __future__ import annotations

import argparse
import json
import sys

from ._common import _get_memos
from .. import __version__
from ..config import config_path, load_config, resolve, write_config, DEFAULTS, ENV_MAP


def cmd_serve(ns: argparse.Namespace) -> None:
    """Start the REST API server."""
    try:
        import uvicorn
    except ImportError:
        print("Error: install memos[server] first", file=sys.stderr)
        sys.exit(1)

    from ..api import create_fastapi_app

    kwargs: dict = {}
    import os

    backend = os.environ.get("MEMOS_BACKEND", getattr(ns, "backend", "memory"))
    kwargs["backend"] = backend
    if backend == "chroma":
        # Support MEMOS_CHROMA_URL (docker-compose) or individual flags
        chroma_url = os.environ.get("MEMOS_CHROMA_URL", "")
        if chroma_url and "//" in chroma_url:
            from urllib.parse import urlparse
            parsed = urlparse(chroma_url)
            kwargs["chroma_host"] = parsed.hostname or "localhost"
            kwargs["chroma_port"] = parsed.port or 8000
        else:
            kwargs["chroma_host"] = getattr(ns, "chroma_host", "localhost")
            kwargs["chroma_port"] = getattr(ns, "chroma_port", 8000)

    app = create_fastapi_app(**kwargs)
    uvicorn.run(app, host=ns.host, port=ns.port)




def cmd_mcp_serve(ns: argparse.Namespace) -> None:
    """Start MCP HTTP server."""
    from ..mcp_server import create_mcp_app
    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn is required. Install with: pip install memos[server]", file=sys.stderr)
        sys.exit(1)
    memos = _get_memos(ns)
    app = create_mcp_app(memos)
    host = getattr(ns, "host", "0.0.0.0")
    port = getattr(ns, "port", 8200)
    print(f"MemOS MCP server listening on http://{host}:{port}/mcp")
    uvicorn.run(app, host=host, port=port, log_level="info")


def cmd_mcp_stdio(ns: argparse.Namespace) -> None:
    """Start MCP server over stdio."""
    from ..mcp_server import run_stdio
    memos = _get_memos(ns)
    run_stdio(memos)




def cmd_config(ns: argparse.Namespace) -> None:
    """Manage CLI configuration."""
    action = getattr(ns, "config_action", None)
    if not action:
        print(f"Config file: {config_path()}")
        print(f"Exists: {config_path().is_file()}")
        print("Use: memos config [show|path|set|init]")
        return

    if action == "path":
        print(str(config_path()))
    elif action == "show":
        cfg = resolve()
        if getattr(ns, "json", False):
            print(json.dumps(cfg, indent=2, default=str))
        else:
            p = config_path()
            print(f"# Resolved config (file={p}, exists={p.is_file()})")
            for k, v in cfg.items():
                src = "default"
                file_cfg = load_config()
                env_val = os.environ.get({v_: k_ for k_, v_ in ENV_MAP.items()}.get(k, ""))
                if k in file_cfg:
                    src = "file"
                if env_val is not None:
                    src = "env"
                print(f"  {k} = {v!r}  ({src})")
    elif action == "set":
        existing = load_config() if config_path().is_file() else {}
        for pair in ns.key_value:
            if "=" not in pair:
                print(f"Error: expected key=value, got '{pair}'", file=sys.stderr)
                sys.exit(1)
            key, val = pair.split("=", 1)
            if key not in DEFAULTS:
                print(f"Error: unknown key '{key}'. Valid: {', '.join(sorted(DEFAULTS))}", file=sys.stderr)
                sys.exit(1)
            # Type coercion
            if isinstance(DEFAULTS[key], bool):
                existing[key] = val.lower() in ("true", "1", "yes")
            elif isinstance(DEFAULTS[key], int):
                existing[key] = int(val)
            elif isinstance(DEFAULTS[key], float):
                existing[key] = float(val)
            else:
                existing[key] = val
        p = write_config(existing)
        print(f"✓ Config written to {p}")
    elif action == "init":
        p = config_path()
        if p.is_file() and not ns.force:
            print(f"Config exists: {p} (use --force to overwrite)", file=sys.stderr)
            sys.exit(1)
        write_config({}, p)
        print(f"✓ Default config created at {p}")
