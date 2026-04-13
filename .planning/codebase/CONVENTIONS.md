# Coding Conventions

**Analysis Date:** 2026-04-13

## Naming Patterns

**Files:**
- Module files: `snake_case.py` (e.g., `dedup.py`, `config.py`, `embedding_cache.py`)
- Package directories: `snake_case` (e.g., `src/memos/storage/`, `src/memos/retrieval/`)
- Test files: `test_*.py` (e.g., `test_core.py`, `test_config.py`)

**Functions and Methods:**
- Functions: `snake_case` (e.g., `generate_id()`, `_build_hash_index()`, `keyword_score()`)
- Private/internal functions: `_leading_underscore()` (e.g., `_tokenize()`, `_normalize()`)
- Class methods: `snake_case` (e.g., `setup_method()`, `test_learn_basic()`)
- Async functions: `async def snake_case()` (e.g., `async def recall_stream()`, `async def consolidate_async()`)

**Variables:**
- Local variables: `snake_case` (e.g., `item_id`, `chunk_size`, `semantic_weight`)
- Constants: `UPPER_CASE` (e.g., `DEFAULTS`, `ENV_MAP`)
- Private module variables: `_leading_underscore` (e.g., `_hash_index`)

**Classes:**
- Main classes: `PascalCase` (e.g., `MemOS`, `StorageBackend`, `RetrievalEngine`)
- Dataclasses: `PascalCase` (e.g., `MemoryItem`, `RecallResult`, `ScoreBreakdown`)

**Protocols and Abstract Classes:**
- Same as regular classes: `PascalCase` (e.g., `Embedder`, `StorageBackend`)

## Code Style

**Formatting:**
- Tool: `ruff` (linter and formatter)
- Line length: 120 characters (configured in `pyproject.toml`)
- Python version: 3.11+

**Linting Configuration** (`pyproject.toml`):
```toml
[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I"]  # Error, Pyflakes, Warning, Import-sorting
ignore = ["E501"]  # Line too long (handled by formatter)
```

**Docstring Style:**
- Module docstrings: Present at top of file, describe purpose
- Class docstrings: Describe the class and usage patterns with examples
- Function docstrings: Present for public APIs; use standard format with Args/Returns/Raises
- Example from `core.py`:
  ```python
  class MemOS:
      """Memory Operating System for LLM Agents.
      
      Usage:
          mem = MemOS(backend="memory")
          mem.learn("User prefers concise responses", tags=["preference"])
          results = mem.recall("how should I respond?")
          mem.prune(threshold=0.3)
      """
  ```

**Type Hints:**
- Use strict type hints throughout (Python 3.11 syntax)
- `from __future__ import annotations` at top of every module for forward references
- Union types use `|` operator: `Optional[str]` or `str | None`
- Always annotate function returns: `-> None`, `-> dict[str, Any]`, `-> RecallResult`
- Avoid `Any` unless justified with a comment

**Imports:**
- Order: Standard library, third-party, local imports (separated by blank lines)
- Conditional imports with try/except for optional dependencies (e.g., `tomllib` vs `tomli`)
- Use `from __future__ import annotations` at module top for PEP 563 compatibility
- Import type-checking-only imports inside `if TYPE_CHECKING:` block

## Error Handling

**Patterns:**
- Raise `ValueError` for invalid input validation (e.g., empty content, invalid TTL format)
- Log exceptions at info/debug level before raising if relevant context exists
- Silent exception handling (bare `except Exception:`) used sparingly; log before continuing
- Example from `core.py`:
  ```python
  if not content.strip():
      raise ValueError("Memory content cannot be empty")
  if sanitize:
      issues = sanitizer.check(content)
      if issues:
          raise ValueError(f"Memory failed sanitization: {issues}")
  ```

**Validation:**
- Input validation happens early in functions
- Range/bound validation (e.g., importance clamping) happens in `learn()` not in models
- Explicit checks before operations (e.g., check if item exists before deleting)

## Logging

**Framework:** `logging` (standard library)

**Setup Pattern:**
```python
import logging
logger = logging.getLogger(__name__)
```

**Usage Patterns:**
- `logger.info()` for significant operations (learning, forgetting, recalls)
- `logger.debug()` for low-level details (embedding caching, index builds)
- Never log full content in production (truncate or hash if needed)
- Example from `core.py`:
  ```python
  logger.info(
      f"Learned: {item.id[:8]}... ({len(item.content)} chars, "
      f"tags={item.tags}, importance={item.importance})"
  )
  ```

## Comments

**When to Comment:**
- Complex algorithms (e.g., BM25 scoring, dedup trigram matching) get detailed comments
- Workarounds and rationale for non-obvious choices (e.g., lazy imports for optional deps)
- Business logic constraints (e.g., "Only enable client-side Ollama embeddings when...")
- Section dividers in test files (e.g., `# -----------\n# 1. Identity\n# -----------`)

**JSDoc/TSDoc:**
- Not used (Python docstrings only)
- Dataclass fields don't need inline documentation (self-evident names)

## Function Design

**Size:**
- Functions typically 20-40 lines
- Larger functions (100+ lines) are typically test files or top-level orchestrators
- Most pure utility functions stay under 20 lines
- Example: `_tokenize()`, `_normalize()` in retrieval are 5-10 lines each

**Parameters:**
- Required params before keyword-only params
- Use `*` to enforce keyword-only: `def __init__(self, store: StorageBackend, *, namespace: str = "")`
- Default values for optional params: `threshold: float = 0.95`
- Avoid long parameter lists (max 5-6 before considering a config object)

**Return Values:**
- Always explicitly return; avoid implicit `None` returns
- Use dataclasses for complex returns (e.g., `DedupCheckResult`, `RecallResult`)
- Single-line returns for simple cases; multi-line for complex logic

## Module Design

**Exports:**
- Public API via `__init__.py` with `__all__` list
- Example from `src/memos/__init__.py`:
  ```python
  __all__ = [
      "MemOS",
      "MemoryItem",
      "RecallResult",
      "MemoryStats",
      "MigrationEngine",
      "MigrationReport",
      "BrainSearch",
      "BrainSearchResult",
      "MarkdownExporter",
      "MarkdownExportResult",
  ]
  ```

**Barrel Files:**
- `__init__.py` files re-export commonly used classes from submodules
- Storage backends live in `src/memos/storage/` with `__init__.py` exposing base class
- Each backend (Chroma, Qdrant, Pinecone) is a separate file imported on demand

**Submodule Organization:**
- Single responsibility: `config.py` handles configuration, `models.py` data structures
- Large modules (>500 lines) get split: `core.py` is monolithic main class, but `retrieval/engine.py` and `consolidation/engine.py` separate concerns
- Private submodules with `_` prefix for internal utilities (e.g., `_common.py` for CLI helpers)

## Async/Concurrency

**Pattern:**
- Async functions use `async def` and `await`
- Async sleep for yielding: `await asyncio.sleep(0)` to let other coroutines run
- No raw thread/process usage; async/await throughout
- Test async code with `pytest-asyncio` (configured in `pyproject.toml`)

---

*Convention analysis: 2026-04-13*
