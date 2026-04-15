# Testing Patterns

**Analysis Date:** 2026-04-15

## Test Framework

**Runner:**
- `pytest` >= 7.0
- Config: `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`

**Async support:**
- `pytest-asyncio` >= 0.23 — used with `@pytest.mark.asyncio`
- `anyio` markers (`@pytest.mark.anyio`) also present in some test files

**Coverage:**
- `pytest-cov` >= 4.0
- Source: `memos` package (`[tool.coverage.run] source = ["memos"]`)
- Reports: `show_missing = true`, `skip_empty = true`
- Coverage uploaded to Codecov for Python 3.11 CI run

**Time freezing:**
- `freezegun` >= 1.2 available in dev extras (used for TTL and decay time-sensitive tests)

**Run Commands:**
```bash
pytest -q --tb=short --cov=memos --cov-report=xml   # full suite with coverage (CI)
pytest tests/test_core.py                            # single file
pytest tests/test_core.py::TestMemOSInMemory         # single class
pytest tests/test_core.py::TestMemOSInMemory::test_learn_basic  # single test
pytest -q --tb=short                                 # all tests, quiet
```

## Test File Organization

**Location:**
- All tests in flat `tests/` directory at project root
- No mirroring of `src/memos/` sub-package structure
- One test file per major module or feature area

**Naming:**
- `test_<module_or_feature>.py` — e.g., `test_core.py`, `test_api_memory.py`, `test_decay.py`
- API tests broken out by concern: `test_api_memory.py`, `test_api_admin.py`, `test_api_recall_filters.py`, `test_api_versioning.py`

**Count:** 70 test files covering all major subsystems.

## Test Structure

**Suite Organization:**
- Classes used for related test groups: `class TestMemOSInMemory`, `class TestSanitizer`, `class TestDecayEngine`
- Module-level functions used for async tests and simple one-shot cases
- `setup_method` used (not `setUp`) for class-level state initialization:

```python
class TestMemOSInMemory:
    def setup_method(self):
        self.mem = MemOS(backend="memory", sanitize=False)

    def test_learn_basic(self):
        item = self.mem.learn("User prefers dark mode", tags=["preference"])
        assert item.content == "User prefers dark mode"
```

**Fixtures defined in `tests/conftest.py`:**
- `memos_empty` — bare `MemOS(backend="memory")` instance
- `mem` — alias for `memos_empty` (backward compat)
- `memos_with_sample_data` — pre-populated with 3 memories (alpha, beta, gamma)
- `kg` — `KnowledgeGraph(db_path=":memory:")` with `yield` + `graph.close()` teardown
- `app` — FastAPI test app wrapping `memos_empty`
- `client` — `starlette.testclient.TestClient` wrapping `app`

**Local fixture override:** Many test files define their own `memos`, `app`, `client` fixtures to control exact state. This is the preferred pattern for isolated API tests.

## Mocking

**Framework:** `unittest.mock` (standard library — `MagicMock`, `patch`)

**Pattern — patching time:**
```python
from unittest.mock import patch

with patch("memos.models.time.time", return_value=future_time):
    item.touch()
```

**Pattern — mocking external client (Chroma example):**
```python
# tests/test_chroma.py
from unittest.mock import MagicMock, patch

def _make_item(**overrides): ...  # local factory

@patch("memos.storage.chroma_backend.chromadb")
def test_upsert(mock_chroma):
    mock_chroma.Client.return_value = MagicMock()
    ...
```

**What to mock:**
- External service clients: Chroma, Qdrant, Pinecone (never require live servers)
- `time.time` for decay / TTL tests
- Network calls (Ollama embedding endpoint)

**What NOT to mock:**
- `MemOS(backend="memory")` — always use the real in-memory backend for business logic tests
- SQLite KnowledgeGraph — use `:memory:` path, not a mock

## Fixtures and Factories

**Test data factories (module-level helpers):**
```python
# Common pattern across test files
def _make_item(content: str, age_days: float = 0, importance: float = 0.5) -> MemoryItem:
    return MemoryItem(
        id=f"test-{content[:8]}",
        content=content,
        importance=importance,
        created_at=time.time() - age_days * 86400,
    )

def _item(content: str, **kw) -> MemoryItem:
    kw.setdefault("id", uuid.uuid4().hex[:12])
    return MemoryItem(content=content, **kw)
```

**API test helper:**
```python
def _learn(client: TestClient, content: str = "test memory", **kwargs) -> str:
    """POST /learn and return the new item's ID."""
    payload = {"content": content}
    payload.update(kwargs)
    resp = client.post("/api/v1/learn", json=payload)
    assert resp.status_code == 200, f"learn failed: {resp.text}"
    return resp.json()["id"]
```

**Location:** All fixtures and factories defined locally in each test file or in `tests/conftest.py`. No separate `fixtures/` directory.

## Coverage

**Requirements:** No minimum threshold enforced in config.

**CI:** Coverage collected on every test run (`--cov=memos --cov-report=xml`) and uploaded to Codecov for Python 3.11.

**View coverage:**
```bash
pytest --cov=memos --cov-report=html
open htmlcov/index.html
```

## Test Types

**Unit Tests:**
- The dominant type — pure Python, no external services
- Use `MemOS(backend="memory")` as the real-but-lightweight backend
- Cover: core logic, models, sanitizer, decay, BM25, consolidation, dedup, compression, versioning, tagger, namespaces, MCP dispatch, CLI commands

**Integration / API Tests:**
- `starlette.testclient.TestClient` used to test the full FastAPI stack in-process
- Files: `test_api_memory.py`, `test_api_admin.py`, `test_api_recall_filters.py`, `test_api_versioning.py`, `test_dashboard.py`, `test_streaming.py`, `test_websocket.py`
- No live HTTP server required — TestClient runs the ASGI app in-process

**Backend Tests (mocked externals):**
- `test_chroma.py`, `test_qdrant.py`, `test_pinecone.py` — use `unittest.mock` to avoid live service dependencies
- `test_json_backend.py` — uses temp filesystem

**Async Tests:**
- `test_async.py` — `AsyncWrapper` over `InMemoryBackend`, concurrent read/write scenarios
- `test_async_consolidation.py`, `test_dashboard.py`, `test_palace.py` — `@pytest.mark.asyncio` or `@pytest.mark.anyio`

**E2E / Docker Tests:**
- `test_docker.py` — checks Docker image build/config (CI-facing)

## What Is Tested

- Core `MemOS` CRUD: learn, recall, forget, prune, stats (`test_core.py`)
- All FastAPI REST endpoints: full request/response shape validation (`test_api_memory.py`, `test_api_admin.py`)
- Decay engine: score adjustment, reinforcement, run_decay, find_prune_candidates (`test_decay.py`)
- Consolidation engine (sync + async) (`test_consolidation.py`, `test_async_consolidation.py`)
- Knowledge Graph: entity CRUD, fact extraction, backlinks, paths, timeline (`test_knowledge_graph.py`, `test_kg_*.py`)
- Versioning: history, diff, rollback, snapshot, gc (`test_versioning.py`, `test_api_versioning.py`)
- MCP server: tool dispatch, all 15 MCP tools (`test_mcp_server.py`, `test_mcp_hooks.py`)
- CLI commands: memory, versioning, namespace, IO (`test_cli.py`, `test_cli_versioning.py`)
- Storage backends: in-memory, JSON, Chroma (mocked), Qdrant (mocked), Pinecone (mocked) (`test_json_backend.py`, `test_chroma.py`, etc.)
- Ingest pipeline: chunker, miner, cache, URL fetch, conversation parsing (`test_ingest.py`, `test_miner.py`)
- Export: Parquet, Markdown, Obsidian vault (`test_parquet.py`, `test_export_markdown.py`, `test_export_obsidian.py`)
- Sanitizer, encryption, TTL, dedup, compression, tagger, analytics, namespaces ACL, sharing, subscriptions, palace, wiki

## What Is NOT Tested (gaps)

- **`src/memos/web/js/`** — No JavaScript tests. The dashboard JS (`graph.js`, `wiki.js`, `state.js`, `controls.js`, etc.) has zero automated test coverage.
- **`src/memos/benchmark.py` / `src/memos/benchmark_quality.py`** — `test_benchmark.py` and `test_benchmark_quality.py` exist in `__pycache__` but not as source files in `tests/`. Coverage of benchmark accuracy is likely shallow.
- **Live embedding integration** — Ollama endpoint (`http://localhost:11434`) is never called in tests; all semantic scoring falls back to keyword-only. Real embedding quality is untested in CI.
- **Live external backends** — Chroma, Qdrant, Pinecone are always mocked; no integration tests against real running services.
- **`src/memos/brain.py`** — Only `test_brain_search.py` covers this, and it mocks the embedding layer.
- **`src/memos/wiki_living.py`** — `test_wiki_living.py` exists but coverage of the living-wiki rebuild pipeline may be partial.
- **No test coverage enforcement** — No minimum threshold means coverage regressions are silent.

---

*Testing analysis: 2026-04-15*
