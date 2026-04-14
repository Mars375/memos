"""MemOS configuration — layered config from file, env, and CLI args.

Resolution order (highest priority first):
  1. CLI arguments
  2. Environment variables (MEMOS_*)
  3. Config file (~/.memos.toml or MEMOS_CONFIG)
  4. Built-in defaults
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ._constants import (
    DEFAULT_CONSOLIDATION_THRESHOLD,
    DEFAULT_DECAY_RATE,
    DEFAULT_EMBED_TIMEOUT,
    DEFAULT_IMPORTANCE,
    DEFAULT_MAX_CHUNK_SIZE,
    DEFAULT_SEMANTIC_WEIGHT,
    DEFAULT_VECTOR_SIZE,
)

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

DEFAULTS: dict[str, Any] = {
    "backend": "memory",
    "chroma_host": "localhost",
    "chroma_port": 8000,
    "qdrant_host": "localhost",
    "qdrant_port": 6333,
    "qdrant_api_key": "",
    "qdrant_path": "",
    "vector_size": DEFAULT_VECTOR_SIZE,
    "semantic_weight": DEFAULT_SEMANTIC_WEIGHT,
    "embed_host": "localhost",
    "embed_model": "nomic-embed-text",
    "embed_port": 11434,
    "embed_timeout": DEFAULT_EMBED_TIMEOUT,
    "persist_path": "",
    "pinecone_api_key": "",
    "pinecone_environment": "",
    "pinecone_index_name": "memos",
    "pinecone_cloud": "aws",
    "pinecone_region": "us-east-1",
    "pinecone_serverless": True,
    "host": "127.0.0.1",
    "port": 8000,
    "sanitize": True,
    "decay_rate": DEFAULT_DECAY_RATE,
    "default_importance": DEFAULT_IMPORTANCE,
    "consolidation_threshold": DEFAULT_CONSOLIDATION_THRESHOLD,
    "max_chunk_size": DEFAULT_MAX_CHUNK_SIZE,
    "api_key": "",
}

ENV_MAP: dict[str, str] = {
    "backend": "MEMOS_BACKEND",
    "chroma_host": "MEMOS_CHROMA_HOST",
    "chroma_port": "MEMOS_CHROMA_PORT",
    "qdrant_host": "MEMOS_QDRANT_HOST",
    "qdrant_port": "MEMOS_QDRANT_PORT",
    "qdrant_api_key": "MEMOS_QDRANT_API_KEY",
    "qdrant_path": "MEMOS_QDRANT_PATH",
    "embed_host": "MEMOS_EMBED_HOST",
    "embed_model": "MEMOS_EMBED_MODEL",
    "embed_timeout": "MEMOS_EMBED_TIMEOUT",
    "persist_path": "MEMOS_PERSIST_PATH",
    "pinecone_api_key": "MEMOS_PINECONE_API_KEY",
    "pinecone_environment": "MEMOS_PINECONE_ENVIRONMENT",
    "pinecone_index_name": "MEMOS_PINECONE_INDEX_NAME",
    "pinecone_cloud": "MEMOS_PINECONE_CLOUD",
    "pinecone_region": "MEMOS_PINECONE_REGION",
    "pinecone_serverless": "MEMOS_PINECONE_SERVERLESS",
    "host": "MEMOS_HOST",
    "port": "MEMOS_PORT",
    "api_key": "MEMOS_API_KEY",
}


def config_path() -> Path:
    """Return the config file path (MEMOS_CONFIG env or ~/.memos.toml)."""
    env = os.environ.get("MEMOS_CONFIG")
    if env:
        return Path(env)
    return Path.home() / ".memos.toml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config from TOML file. Returns empty dict if missing or unreadable."""
    if tomllib is None:
        return {}
    p = path or config_path()
    if not p.is_file():
        return {}
    try:
        with open(p, "rb") as f:
            data = tomllib.load(f)
        # Flatten top-level [memos] section
        return data.get("memos", data)
    except Exception:
        return {}


def resolve(cli_args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve merged config: defaults < file < env < cli_args."""
    result = dict(DEFAULTS)

    # Layer 2: config file
    file_cfg = load_config()
    for k, v in file_cfg.items():
        if k in DEFAULTS:
            result[k] = v

    # Layer 3: environment
    for key, env_var in ENV_MAP.items():
        val = os.environ.get(env_var)
        if val is not None:
            # Type coercion for known int/bool keys
            if key in ("chroma_port", "embed_port", "port", "qdrant_port", "vector_size", "embed_timeout") and val:
                result[key] = int(val)
            elif key in ("sanitize", "pinecone_serverless"):
                result[key] = val.lower() not in ("0", "false", "no")
            else:
                result[key] = val

    # Layer 4: CLI args (only non-None / non-default values)
    if cli_args:
        for k, v in cli_args.items():
            if v is not None and k in DEFAULTS:
                result[k] = v

    return result


def write_config(
    values: dict[str, Any],
    path: Path | None = None,
) -> Path:
    """Write a minimal TOML config file. Creates parent dirs as needed."""
    p = path or config_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    lines = ["# MemOS CLI configuration\n", "[memos]\n"]
    for k, v in values.items():
        if k not in DEFAULTS:
            continue
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}\n")
        elif isinstance(v, str):
            lines.append(f'{k} = "{v}"\n')
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}\n")
    p.write_text("".join(lines))
    return p
