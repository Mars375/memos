# MemOS Audit Fix Plan

> Generated from comprehensive codebase audit — 2026-04-14
> Status: IN PROGRESS

## Sprint 1 — Security Critical (5 tasks)

### S1.1 WebSocket Auth on `/ws`
- **File**: `src/memos/api/routes/admin.py:152-156`
- **Fix**: Validate `X-API-Key` from WebSocket handshake headers before `accept()`
- **Pattern**: Check `key_manager.validate()` from headers, close with 4001 if invalid

### S1.2 Auth on Standalone MCP App
- **File**: `src/memos/mcp_server.py:760` (`create_mcp_app()`)
- **Fix**: Add auth middleware to standalone MCP FastAPI app, same as main app
- **Pattern**: Import and reuse `create_auth_middleware` from `api/auth.py`

### S1.3 CORS Default Restriction
- **File**: `src/memos/mcp_server.py:34`
- **Fix**: Change default from `"*"` to `"http://localhost:8100"`
- **Also**: Add `CORSMiddleware` to main API app (`api/__init__.py`)

### S1.4 Auth-Disabled Startup Warning
- **File**: `src/memos/api/auth.py` or `api/__init__.py`
- **Fix**: Log prominent `WARNING` when `auth_enabled=False` at startup

### S1.5 Replace Custom Crypto with Fernet
- **File**: `src/memos/crypto.py`
- **Fix**: Replace hand-rolled XOR cipher with `cryptography.fernet.Fernet`
- **Keep**: PBKDF2 key derivation (good), just use it to derive a Fernet key
- **MUST**: Maintain same `encrypt/decrypt` API signature
- **MUST**: Add migration path for existing encrypted data

## Sprint 2 — API & Validation (5 tasks)

### S2.1 Pydantic Request Models
- **Files**: `src/memos/api/routes/memory.py`, `knowledge.py`, `admin.py`
- **Fix**: Create `src/memos/api/schemas.py` with Pydantic `BaseModel` for all endpoints
- **Models needed**: LearnRequest, RecallRequest, BatchLearnRequest, SearchRequest, ForgetRequest, PruneRequest, ConsolidateRequest, FeedbackRequest, FactRequest, EntityQueryRequest, etc.
- **MUST**: Add field validators for importance (0-1), tags (list[str]), content (max length)

### S2.2 Proper HTTP Status Codes
- **Files**: All route files (31 endpoints)
- **Fix**: Return `JSONResponse(status_code=400/404/422/500)` instead of always 200
- **Mapping**: validation error → 400, not found → 404, bad input → 422, server error → 500

### S2.3 Unified Error Response Schema
- **Files**: All route files
- **Fix**: Standardize on `{"status": "error", "message": "...", "code": "ERROR_CODE"}`
- **Create**: `api/errors.py` with `error_response(message, code, status_code)` helper

### S2.4 Stop Leaking Exceptions
- **Files**: 27+ instances across routes
- **Fix**: Replace `str(exc)` with generic messages in production, log full exception server-side
- **Pattern**: `except Exception as exc: logger.error(...); return error_response("Internal error", status_code=500)`

### S2.5 Sanitizer Enforcement
- **File**: `src/memos/api/routes/memory.py` (learn endpoint)
- **Fix**: Call `MemorySanitizer.is_safe()` before storing, reject if unsafe
- **Add**: `MEMOS_ENFORCE_SANITIZATION` env var (default: true)

## Sprint 3 — Architecture Decoupling (4 tasks)

### S3.1 Public Methods on MemOS
- **File**: `src/memos/core.py`
- **Fix**: Add public methods that proxy private attributes:
  - `store` property → returns `self._store`
  - `decay_engine` property → returns `self._decay`
  - `current_namespace` property → returns `self._namespace`
  - `kg_engine` property → returns `self._kg`
  - `kg_bridge` property → returns `self._kg_bridge`
- **Then**: Update all 8 violating modules to use public properties

### S3.2 Extract Shared Utils
- **Create**: `src/memos/utils.py`
- **Move**: `_coerce_tags()` (from core.py), `_parse_date()` (from knowledge_graph.py), `_get_or_create_kg()` (from mcp_server.py)
- **Update**: All callers to import from utils

### S3.3 Add Logging to Silent Exceptions
- **Files**: 29 `except Exception: pass` blocks across 15 files
- **Fix**: Add `logger.debug()` or `logger.warning()` before each `pass`
- **Priority**: core.py, qdrant_backend.py (10), mcp_hooks.py (5)

### S3.4 Dead Code Cleanup
- `wiki_living.py:743` — duplicate `return result` (unreachable)
- `mcp_server.py:777` — discarded `str(uuid.uuid4())`
- `mcp_server.py:838` — MCP version mismatch (`"2024-11-05"` vs `"2025-03-26"`)

## Sprint 4 — Code Quality (4 tasks)

### S4.1 Type Hints on API Handlers
- **Files**: 97 async handlers in memory.py, knowledge.py, admin.py
- **Fix**: Add `-> dict[str, Any]` return types to all handlers
- **Fix**: Type all factory function parameters

### S4.2 Move Inline Imports to Top-Level
- **Files**: `acl.py` (6x `import time`), `memory.py` (3x `from datetime`), `parsers.py` (6x `import datetime`)
- **Fix**: Move stdlib imports to module top-level; keep lazy imports only for heavy third-party

### S4.3 Name Magic Numbers
- **Files**: `brain.py`, `consolidation/engine.py`, `compression.py`, `core.py`
- **Fix**: Extract named constants at module/class level

### S4.4 MCP Server Cleanup
- Extract 298L JSON schema to `src/memos/mcp_schemas.py`
- Deduplicate dispatch logic between `add_mcp_routes()` and `create_mcp_app()`
- Remove `_Stub` workaround class in `commands_memory.py`

## Sprint 5 — Tests (4 tasks)

### S5.1 Shared conftest.py
- **Create**: `tests/conftest.py` with shared fixtures
- **Fixtures**: `memos_instance`, `app`, `client`, `in_memory_store`
- **Eliminate**: 60 duplicated fixture definitions across test files

### S5.2 Tests for Uncovered Modules
- **Create**: `tests/test_events.py` for events.py (0 coverage)
- **Create**: `tests/test_query.py` for query.py (0 coverage)
- **Create**: `tests/test_crypto.py` for crypto.py (0 coverage, security-critical)

### S5.3 API Route Tests
- **Create**: `tests/test_api_memory.py` for routes/memory.py (616L, 0 dedicated test)
- **Create**: `tests/test_api_admin.py` for routes/admin.py (398L, 0 dedicated test)
- **Expand**: `tests/test_knowledge_graph.py` for routes/knowledge.py REST endpoints

### S5.4 Fix Test Smells
- Replace 114 `time.sleep()` with `freezegun` or mock
- Replace 16 hardcoded `/tmp/` paths with `tmp_path` fixture
- Add pytest markers: `@pytest.mark.integration`, `@pytest.mark.slow`
