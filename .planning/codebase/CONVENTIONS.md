# Coding Conventions

**Analysis Date:** 2026-04-15

## Code Style

**Formatting:**
- Tool: `ruff format` (configured in `pyproject.toml`)
- Line length: 120 characters
- All source and test files are ruff-formatted; CI enforces `ruff format --check src/ tests/`

**Linting:**
- Tool: `ruff check` with rules `E`, `F`, `W`, `I` (pycodestyle errors/warnings, pyflakes, isort)
- `E501` (line too long) is explicitly ignored — line length is advisory via formatter, not enforced as a lint error
- Target: Python 3.11+
- Checked in CI on every push and PR to `main`

**Type hints:**
- All function signatures carry type annotations
- `Optional[X]` is used (not `X | None`), consistent with Python 3.11 target
- `from __future__ import annotations` is present in **every** source file (all 83 modules) and in all test files
- `typing.Any` is used sparingly; no untyped `dict` or `list` in public APIs
- `TYPE_CHECKING` guard used for imports that would create circular dependencies (e.g., `src/memos/retrieval/engine.py`)

## Naming Patterns

**Modules / files:**
- `snake_case.py` throughout — e.g., `mcp_server.py`, `knowledge_graph.py`, `async_wrapper.py`
- Sub-packages use short, descriptive names: `api/`, `cli/`, `storage/`, `ingest/`, `retrieval/`, `versioning/`, `consolidation/`, `decay/`, `namespaces/`, `sharing/`, `cache/`, `compaction/`, `subscriptions/`, `embeddings/`
- CLI command modules are prefixed: `commands_memory.py`, `commands_knowledge.py`, `commands_io.py`, etc.
- Internal helpers prefixed with `_`: `_constants.py`, `_common.py`, `_parser.py`

**Classes:**
- `PascalCase` — e.g., `MemOS`, `MemoryItem`, `StorageBackend`, `DecayEngine`, `RetrievalEngine`, `KnowledgeGraph`
- Dataclasses used for plain data models (`MemoryItem`, `RecallResult`, `ScoreBreakdown`, `DecayConfig`)
- ABCs named with `Backend` suffix: `StorageBackend`, `AsyncStorageBackend`
- Protocol classes named with role: `Embedder` in `src/memos/retrieval/engine.py`

**Functions:**
- `snake_case` for all public functions and methods
- Private helpers prefixed with `_`: `_bm25_score`, `_get_embedding`, `_dispatch`, `_make_item` (in tests)
- Factory helper functions in tests named `_make_*` or `_item(...)`

**Variables:**
- `snake_case`; instance attributes with `_` prefix for private: `self._store`, `self._embed_host`
- Constants: `SCREAMING_SNAKE_CASE` in `src/memos/_constants.py` — e.g., `DEFAULT_MAX_MEMORIES`, `SECONDS_PER_DAY`
- Numeric constants use underscores for readability: `86_400`, `10_000`, `50_000`

**Test helpers:**
- Module-level helper functions prefixed `_`: `_learn()`, `_make_item()`, `_make_envelope()`, `_chroma_results()`

## File Organization Rules

**Source layout:**
```
src/memos/
├── __init__.py, _constants.py   # package root + all domain constants
├── core.py                      # main MemOS class (entry point)
├── models.py                    # dataclasses: MemoryItem, RecallResult, etc.
├── api/                         # FastAPI app + routes + middleware
├── cli/                         # argparse CLI commands
├── storage/                     # pluggable backends (base.py, *_backend.py)
├── retrieval/                   # hybrid search engine
├── consolidation/, decay/, ...  # domain sub-packages, each with engine.py
└── web/                         # static dashboard (HTML/CSS/JS)
```

- Every sub-package has `__init__.py`
- Domain engines live in `<feature>/engine.py`; async variants in `<feature>/async_engine.py`
- Data models for a sub-package live in `<feature>/models.py`
- Persistent storage for a sub-package lives in `<feature>/persistent_store.py` or `<feature>/store.py`
- Tests live in a flat `tests/` directory at project root (not mirroring `src/` hierarchy)

## Patterns Used

**Abstract Base Classes:**
- `StorageBackend` in `src/memos/storage/base.py` — all backends implement this ABC; keyword-only `namespace=""` parameter on every method

**Protocols:**
- `Embedder` protocol (`runtime_checkable`) in `src/memos/retrieval/engine.py` — pluggable embedding providers

**Dataclasses:**
- Used for all domain data objects (`MemoryItem`, `ScoreBreakdown`, `RecallResult`, `DecayConfig`, etc.)
- `field(default_factory=...)` used for mutable defaults

**Constants module:**
- All magic numbers defined in `src/memos/_constants.py` and imported explicitly; never hardcoded in logic files
- Sections documented with ASCII header comments (`# ── General ────`)

**Optional dependencies:**
- Heavy optional packages (fastapi, chromadb, qdrant-client, pyarrow, sentence-transformers) guarded with `try/except ImportError` at import time; raise a helpful installation message when used without the extras install

**Logging:**
- `logging.getLogger(__name__)` pattern; module-level `logger` variable
- Present in `src/memos/core.py`, `src/memos/retrieval/engine.py`, `src/memos/ingest/miner.py`, and ~12 other modules
- Not present in pure data modules or thin wrappers

**Return types:**
- Dataclass instances returned from engines; never raw `dict` from core logic
- API routes return `dict` (FastAPI serializes from Pydantic models or plain dicts)

## Linting / Formatting

**Config location:** `pyproject.toml` `[tool.ruff]` and `[tool.ruff.lint]`

**Run commands:**
```bash
ruff check src/ tests/           # lint
ruff format src/ tests/          # format in-place
ruff format --check src/ tests/  # format check (CI)
```

**Enforced rules:**
- `E` — pycodestyle errors
- `F` — pyflakes (unused imports, undefined names)
- `W` — pycodestyle warnings
- `I` — isort (import ordering)
- `E501` ignored (line length enforced only by formatter)

**Import order (isort via ruff):**
1. `from __future__ import annotations` (always first line)
2. Standard library
3. Third-party packages
4. Local relative imports (`.module` or `..module`)

---

*Convention analysis: 2026-04-15*
