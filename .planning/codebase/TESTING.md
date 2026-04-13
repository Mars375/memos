# Testing Patterns

**Analysis Date:** 2026-04-13

## Test Framework

**Runner:**
- `pytest` (7.0+)
- Config: `pyproject.toml` with `[tool.pytest.ini_options]`
- Test discovery: All files matching `test_*.py` in `tests/` directory

**Assertion Library:**
- `pytest` built-in assertions (no external library needed)
- `pytest.approx()` for floating-point comparisons
- `pytest.raises()` for exception testing

**Test Dependencies** (`pyproject.toml`):
```toml
dev = ["pytest>=7.0", "pytest-cov>=4.0", "pytest-asyncio>=0.23", "httpx", "ruff>=0.4"]
```

**Run Commands:**
```bash
pytest                          # Run all tests
pytest -v                       # Verbose output
pytest tests/test_core.py       # Run single file
pytest tests/test_core.py::TestMemoryItem::test_touch_updates_access  # Run single test
pytest -k "test_learn"          # Run tests matching pattern
pytest --cov=memos             # Coverage report
pytest -x                       # Stop on first failure
pytest -s                       # Show print output
```

## Test File Organization

**Location:**
- Tests co-located in `tests/` directory (not scattered in `src/`)
- One test file per main module: `src/memos/core.py` → `tests/test_core.py`
- Large modules may have multiple test files: `tests/test_versioning.py`, `tests/test_miner.py`

**Naming:**
- Test files: `test_*.py` (e.g., `test_core.py`, `test_config.py`, `test_retrieval.py`)
- Test classes: `Test*` (e.g., `TestMemoryItem`, `TestMemOSInMemory`, `TestNamespaceIsolation`)
- Test methods: `test_*` (e.g., `test_touch_updates_access`, `test_learn_basic`, `test_recall_keyword`)

**Statistics:**
- 15 test files total in `tests/`
- 1,513 total `def test_` definitions
- Largest test file: `test_knowledge_graph.py` (744 lines)
- Well-distributed coverage across modules

## Test Structure

**Suite Organization:**
```python
class TestMemoryItem:
    """Test group for MemoryItem dataclass."""
    
    def test_touch_updates_access(self):
        item = MemoryItem(id="test", content="hello")
        old_accessed = item.accessed_at
        old_count = item.access_count
        time.sleep(0.01)
        item.touch()
        assert item.accessed_at > old_accessed
        assert item.access_count == old_count + 1

class TestMemOSInMemory:
    """Tests using the in-memory backend — no deps required."""
    
    def setup_method(self):
        """Called before each test method."""
        self.mem = MemOS(backend="memory", sanitize=False)
```

**Patterns:**
- `setup_method()` for per-test initialization (replaces `setUp()`)
- No `teardown_method()` needed in most cases (in-memory state discarded)
- Test fixtures via `@pytest.fixture()` for shared test data
- Test class grouping by functionality (model tests, backend tests, API tests)

**Fixtures:**
```python
@pytest.fixture()
def memos_mem() -> MemOS:
    """In-memory MemOS instance (no embedding, fast)."""
    return MemOS(backend="memory")

@pytest.fixture()
def cs_tmp(memos_mem: MemOS, tmp_path: Path) -> ContextStack:
    """ContextStack with a temporary identity file path."""
    identity_file = tmp_path / "identity.txt"
    return ContextStack(memos_mem, identity_path=str(identity_file))

@pytest.fixture()
def corpus() -> list[str]:
    return [
        "Docker deployment pipeline for kubernetes and helm charts",
        "Python FastAPI backend REST endpoint authentication",
        "React Vue frontend component UI tailwind CSS",
    ]
```

## Mocking

**Framework:** `unittest.mock` (standard library)

**Patterns:**
```python
from unittest.mock import patch, MagicMock

# Patch environment variables
with patch.dict(os.environ, {"MEMOS_BACKEND": "chroma"}, clear=False):
    cfg = resolve()

# Patch function behavior
with patch("memos.config.load_config", return_value={"backend": "chroma"}):
    cfg = resolve()

# Patch module import
with patch("memos.cli.commands_system.config_path", return_value=cfg_file):
    main(["config", "init"])
```

**What to Mock:**
- Environment variables (for config testing)
- File system operations (use `tmp_path` fixture instead where possible)
- External service calls (but only when necessary; prefer in-memory backends for unit tests)
- subprocess/system calls (never actually execute shell commands in tests)

**What NOT to Mock:**
- Core business logic (test actual MemOS behavior, not mocked versions)
- Data models/dataclasses (test as-is)
- In-memory storage backends (fast, safe, no need to mock)
- Standard library functions like `time.time()` (only mock when testing time-dependent behavior)

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture()
def cs_with_memories(cs_tmp: ContextStack) -> ContextStack:
    """ContextStack loaded with a few memories for testing."""
    m = cs_tmp._memos
    m.learn("Python async best practices", tags=["python", "async"], importance=0.9)
    m.learn("Docker multi-stage builds", tags=["devops"], importance=0.85)
    m.learn("Redis caching patterns", tags=["redis", "cache"], importance=0.7)
    m.learn("Git rebase workflow", tags=["git"], importance=0.5)
    return cs_tmp
```

**Location:**
- Fixtures defined at top of test file or in conftest.py
- Use `tmp_path` (pytest built-in) for temporary files
- Use `monkeypatch` (pytest built-in) for patching instead of `unittest.mock` where possible

## Coverage

**Requirements:** None enforced (no coverage threshold in CI/CD)

**View Coverage:**
```bash
pytest --cov=memos --cov-report=html
# Opens htmlcov/index.html in browser
pytest --cov=memos --cov-report=term-missing
```

**Configuration** (`pyproject.toml`):
```toml
[tool.coverage.run]
source = ["memos"]

[tool.coverage.report]
show_missing = true
skip_empty = true
```

## Test Types

**Unit Tests (Primary):**
- Scope: Single function or class in isolation
- Approach: No external services, use in-memory backends
- Example: `TestMemoryItem.test_touch_updates_access()` tests the `touch()` method directly
- Speed: < 1ms per test
- Count: Majority of tests (1,000+)

**Integration Tests:**
- Scope: Multiple components working together
- Approach: Full MemOS instance with in-memory backend
- Example: `TestMemOSInMemory` tests end-to-end learn → recall → forget workflows
- Speed: 1-100ms per test
- Count: ~300 tests

**Config/CLI Tests:**
- Scope: Configuration loading and command-line interface
- Approach: Mock file system, patch environment
- Example: `TestResolve` tests config precedence (defaults < file < env < CLI)
- Uses temporary paths via `tmp_path` fixture

**Async Tests:**
- Scope: Async/await code paths
- Framework: `pytest-asyncio` (configured in `pyproject.toml`)
- Pattern: Mark with `@pytest.mark.asyncio` or use async fixtures
- Example from codebase (implicit async fixtures in test_streaming.py)

**E2E Tests:**
- Not currently used (complex integration would require docker services)
- Could be added for API server testing via `httpx` client

## Common Patterns

**Basic Unit Test:**
```python
class TestTokenizer:
    def test_tokenize_basic(self):
        tokens = _tokenize("Hello World, this is a test!")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_tokenize_empty(self):
        assert _tokenize("") == []
```

**Setup/State Tests:**
```python
class TestMemOSInMemory:
    def setup_method(self):
        self.mem = MemOS(backend="memory", sanitize=False)
    
    def test_learn_basic(self):
        item = self.mem.learn("User prefers dark mode", tags=["preference"])
        assert item.id
        assert item.content == "User prefers dark mode"
        assert item.tags == ["preference"]
```

**Exception Testing:**
```python
def test_learn_empty_raises(self):
    with pytest.raises(ValueError, match="cannot be empty"):
        self.mem.learn("")

def test_parse_ttl_invalid(self):
    with pytest.raises(ValueError, match="Invalid TTL"):
        parse_ttl("xyz")
```

**Floating-Point Assertions:**
```python
def test_normalize_range(self):
    result = _normalize([0.0, 5.0, 10.0])
    assert result[0] == pytest.approx(0.0)
    assert result[1] == pytest.approx(0.5)
    assert result[2] == pytest.approx(1.0)
```

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_recall_stream_async(self):
    mem = MemOS(backend="memory")
    mem.learn("async content")
    results = []
    async for item in mem.recall_stream("async"):
        results.append(item)
    assert len(results) > 0
```

**File I/O Testing:**
```python
def test_set_identity_creates_parent_dirs(memos_mem: MemOS, tmp_path: Path) -> None:
    deep_path = tmp_path / "a" / "b" / "c" / "identity.txt"
    cs = ContextStack(memos_mem, identity_path=str(deep_path))
    cs.set_identity("deep identity")
    assert deep_path.exists()
    assert deep_path.read_text() == "deep identity"
```

## Test Data and Isolation

**Isolation:**
- Each test class with `setup_method()` gets a fresh MemOS instance
- No shared state between tests
- In-memory backend ensures tests don't interfere with each other
- Temporary files via `tmp_path` are automatically cleaned up by pytest

**Determinism:**
- No random seeds needed (most tests are deterministic)
- Time-based tests use `time.sleep()` for short delays
- ID generation is deterministic (SHA-256 hash of content)

---

*Testing analysis: 2026-04-13*
