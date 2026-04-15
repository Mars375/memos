# Phase 1: API Security Hardening - Research

**Researched:** 2026-04-15
**Domain:** FastAPI middleware, Pydantic validation, API security defaults
**Confidence:** HIGH

## Summary

Phase 1 targets eight security requirements across the MemOS REST API layer. The issues are concrete, well-localized, and the fixes are straightforward Python/FastAPI patterns. No external libraries need to be added -- Pydantic models already exist in `schemas.py` but are not wired to 13 endpoints, the rate-limiter middleware has a logic ordering bug, and several defaults need tightening.

The critical fix is the rate-limiter in `auth.py:136-148` which calls `call_next(request)` BEFORE checking `if not allowed` -- this means every over-limit request still executes the full handler with all side effects. The standalone `ratelimit.py` middleware already implements the correct check-first pattern and should be the sole rate-limiting mechanism.

**Primary recommendation:** Fix the 8 issues in dependency order: rate-limiter first (SEC-01), then Pydantic wiring (SEC-02), then defaults and cleanup (SEC-05 through SEC-11). Each fix is independent enough for parallel work but should be verified in order.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEC-01 | Rate-limiter rejects BEFORE handler executes | auth.py:136-148 bug analysis; ratelimit.py already has correct pattern |
| SEC-02 | All 13 POST endpoints use Pydantic models | All 13 schemas exist in schemas.py; direct wiring needed |
| SEC-05 | Auth enabled by default; startup warning when no keys | auth.py:89-90 returns True when no keys; add log warning in create_fastapi_app |
| SEC-06 | Default binding is 127.0.0.1 | CLI serve already defaults to 127.0.0.1; MCP serve defaults to 0.0.0.0 (commands_system.py:57) |
| SEC-07 | CORS default is localhost, not wildcard | mcp_server.py:34 defaults to "*" |
| SEC-09 | Pinecone API key masked in logs | Key stored as self._api_key; could leak in tracebacks; add __repr__ masking and logging filter |
| SEC-10 | Sanitization consolidated to single location | Split between API env var (memory.py:40) and core.py:357; consolidate to core |
| SEC-11 | hmac.compare_digest simplified | auth.py:92 has convoluted expression |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.104 | REST API framework | Already in use; Pydantic integration is native |
| Pydantic | v2 (via FastAPI) | Request validation | Already in use; models exist in schemas.py |
| Starlette | (via FastAPI) | ASGI middleware | Already in use; CORSMiddleware available |
| Python stdlib hmac | 3.11+ | Timing-safe comparison | Already in use; just needs simplification |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| starlette.middleware.cors | (via FastAPI) | CORS management | Could replace manual CORS headers in mcp_server.py |
| logging.Filter | stdlib | Log filtering | For Pinecone API key masking |

No new dependencies are needed. Everything required is already installed.

## Architecture Patterns

### Pattern 1: Middleware Ordering (Check-Before-Dispatch)
**What:** Rate limiting must check and reject BEFORE calling `call_next(request)`.
**When to use:** Any middleware that gates access.
**Current bug (auth.py:136-148):**
```python
# BROKEN: handler runs before rate check
allowed, headers = key_manager.rate_limiter.check(api_key)
response = await call_next(request)  # <-- handler executes HERE
for k, v in headers.items():
    response.headers[k] = v
if not allowed:
    return JSONResponse(status_code=429, ...)  # <-- too late, side effects done
return response
```
**Fix pattern:**
```python
# CORRECT: reject before handler
allowed, headers = key_manager.rate_limiter.check(api_key)
if not allowed:
    return JSONResponse(status_code=429, ..., headers=headers)
response = await call_next(request)
for k, v in headers.items():
    response.headers[k] = v
return response
```

### Pattern 2: Pydantic Model as FastAPI Parameter
**What:** Replace `body: dict` with typed Pydantic model in route signature.
**Current (broken):**
```python
@router.post("/api/v1/kg/facts")
async def kg_add_fact(body: dict):
    subject = body.get("subject", "").strip()
    if not subject:
        return {"status": "error", "message": "subject required"}
```
**Fixed:**
```python
from ..schemas import FactRequest

@router.post("/api/v1/kg/facts")
async def kg_add_fact(body: FactRequest):
    # Pydantic already validated subject is non-empty string
    fact_id = _kg.add_fact(subject=body.subject, ...)
```
FastAPI automatically returns 422 with field-level errors when validation fails. No manual `.get()` checks needed.

### Pattern 3: Logging Filter for Secret Masking
**What:** A `logging.Filter` that redacts API keys from log records.
**When to use:** When secrets may leak through exception tracebacks or debug logs.
```python
import logging
import re

class SecretMaskingFilter(logging.Filter):
    """Mask Pinecone API keys in log output."""
    _PATTERN = re.compile(r'(pcsk_[A-Za-z0-9_-]{8})[A-Za-z0-9_-]+')

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            record.msg = self._PATTERN.sub(r'\1****', record.msg)
        if record.exc_text:
            record.exc_text = self._PATTERN.sub(r'\1****', record.exc_text)
        return True
```

### Pattern 4: Consolidated Sanitization
**What:** Single boolean flag in MemOS controls sanitization; API layer does not have its own toggle.
**Current problem:** `MEMOS_ENFORCE_SANITIZATION` env var in `api/routes/memory.py:40` can desync from `self._sanitize` in `core.py:183`.
**Fix:** Remove the API-layer env var. Let `MemOS.sanitize` be the single source of truth. The API routes should not independently decide whether to sanitize.

### Anti-Patterns to Avoid
- **Dual rate-limiters:** Two `RateLimiter` classes (auth.py sliding-window + ratelimit.py token-bucket) create confusion. Remove the auth.py one, keep only ratelimit.py.
- **Manual validation after Pydantic:** Once a route uses a Pydantic model, do not add redundant `if not body.subject` checks. Trust Pydantic's validation.
- **CORS via manual headers:** The `_CORS_HEADERS` dict in mcp_server.py is fragile. For the MCP routes mounted on the main app, use FastAPI's `CORSMiddleware` or at minimum tighten the default.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request validation | Manual `.get()` + type checks | Pydantic models (already exist in schemas.py) | 13 endpoints duplicate validation logic; Pydantic gives type coercion, min/max, 422 errors for free |
| CORS handling | Manual header dict | `starlette.middleware.cors.CORSMiddleware` or tightened defaults | Manual headers miss preflight edge cases |
| Secret masking | Ad-hoc string replacement | `logging.Filter` subclass | Centralized, catches all log paths including tracebacks |
| Timing-safe comparison | Complex boolean expression | Simple `hmac.compare_digest(a, b)` | Current auth.py:92 expression is obfuscated |

## Common Pitfalls

### Pitfall 1: Pydantic 422 vs Application-Level Error Format
**What goes wrong:** FastAPI returns `{"detail": [...]}` for Pydantic validation errors, but the existing API returns `{"status": "error", "message": "..."}`. Clients may break if they only handle the latter.
**Why it happens:** FastAPI's default validation error handler uses a different format.
**How to avoid:** Add a custom `RequestValidationError` handler in `create_fastapi_app` that wraps Pydantic errors in the `{"status": "error", "message": "..."}` format. This maintains backward compatibility.
**Warning signs:** Client tests expecting `status: error` start getting 422 with `detail` field.

### Pitfall 2: MCP CORS vs API CORS
**What goes wrong:** The MCP routes in `mcp_server.py` set CORS headers manually via `_CORS_HEADERS` dict. The REST API might use `CORSMiddleware`. These can conflict or have different defaults.
**Why it happens:** MCP routes were added independently of the REST API CORS setup.
**How to avoid:** Ensure both MCP and REST endpoints respect the same CORS origin configuration. The MCP `_CORS_ALLOWED_ORIGINS` should read from the same env var or default.
**Warning signs:** MCP works from browser but REST API returns CORS errors, or vice versa.

### Pitfall 3: Rate-Limiter Removal Breaks Auth Middleware
**What goes wrong:** The `APIKeyManager` has a `.rate_limiter` attribute (auth.py:61). Removing the auth.py `RateLimiter` class without updating `APIKeyManager` breaks the auth middleware.
**Why it happens:** Tight coupling between auth and rate-limiting in auth.py.
**How to avoid:** When removing the auth.py `RateLimiter`, also remove the `rate_limiter` attribute from `APIKeyManager` and the rate-limit check block from `create_auth_middleware` (lines 136-148). The standalone `create_rate_limit_middleware` in ratelimit.py handles rate limiting independently.
**Warning signs:** `AttributeError: 'APIKeyManager' object has no attribute 'rate_limiter'`.

### Pitfall 4: MCP Serve Binding Default
**What goes wrong:** `cmd_mcp_serve` in `commands_system.py:57` defaults to `host="0.0.0.0"`, while `cmd_serve` defaults to `127.0.0.1`. Fixing only one leaves the other exposed.
**Why it happens:** The two serve commands were written independently.
**How to avoid:** Fix both: `cmd_mcp_serve` must also default to `127.0.0.1`. The CLI parser at `_parser.py:334` already defaults to `127.0.0.1`, but `commands_system.py:57` uses `getattr(ns, "host", "0.0.0.0")` which overrides it if the attribute is missing.
**Warning signs:** Running `memos mcp-serve` exposes the service on all interfaces.

### Pitfall 5: Sanitization Env Var Removal Breaks Existing Deployments
**What goes wrong:** Users who set `MEMOS_ENFORCE_SANITIZATION=false` lose the ability to disable sanitization.
**Why it happens:** Removing the env var without providing an alternative.
**How to avoid:** The `MemOS` constructor already accepts `sanitize=False`, and config.py supports it. Document that `MEMOS_SANITIZE=false` (via config) replaces the API-layer env var. Alternatively, keep reading the env var but delegate to core.
**Warning signs:** Users report they can no longer disable sanitization.

## Code Examples

### SEC-01: Fix Rate-Limiter in auth.py
The entire rate-limit block (lines 136-148) in `create_auth_middleware` should be removed. Rate limiting is handled by the standalone `create_rate_limit_middleware` in `ratelimit.py`, which already uses the correct check-first pattern. The `RateLimiter` class in auth.py (lines 21-48) and the `rate_limiter` attribute on `APIKeyManager` (line 61) should also be removed.

### SEC-02: Endpoint-to-Schema Mapping
All 13 schemas exist. Here is the mapping:

**knowledge.py (7 endpoints):**
| Endpoint | Current | Schema |
|----------|---------|--------|
| `POST /api/v1/kg/facts` | `body: dict` | `FactRequest` |
| `POST /api/v1/kg/infer` | `body: dict` | `InferRequest` |
| `POST /api/v1/brain/search` | `body: dict` | `BrainSearchRequest` |
| `POST /api/v1/palace/wings` | `body: dict` | `PalaceCreateWingRequest` |
| `POST /api/v1/palace/rooms` | `body: dict` | `PalaceCreateRoomRequest` |
| `POST /api/v1/palace/assign` | `body: dict` | `PalaceAssignRequest` |
| `POST /api/v1/context/identity` | `body: dict` | `ContextIdentityRequest` |

**admin.py (6 endpoints):**
| Endpoint | Current | Schema |
|----------|---------|--------|
| `POST /api/v1/ingest/url` | `body: dict` | `IngestURLRequest` |
| `POST /api/v1/mine/conversation` | `body: dict` | `MineConversationRequest` |
| `POST /api/v1/namespaces/{ns}/grant` | `body: dict` | `ACLGrantRequest` |
| `POST /api/v1/namespaces/{ns}/revoke` | `body: dict` | `ACLRevokeRequest` |
| `POST /api/v1/share/offer` | `body: dict` | `ShareOfferRequest` |
| `POST /api/v1/share/import` | `body: dict` | `ShareImportRequest` |

### SEC-05: Auth Default Warning
```python
# In create_fastapi_app (api/__init__.py), after key_manager creation:
import logging
_log = logging.getLogger("memos.api")
if not key_manager.auth_enabled:
    _log.warning(
        "API authentication is DISABLED (no API keys configured). "
        "Set MEMOS_API_KEY or pass api_keys to enable auth."
    )
```

### SEC-06: Fix MCP Serve Binding
```python
# commands_system.py:57 — change fallback from "0.0.0.0" to "127.0.0.1"
host = getattr(ns, "host", "127.0.0.1")
```

### SEC-07: CORS Default
```python
# mcp_server.py:34 — change default from "*" to "http://localhost:*"
_CORS_ALLOWED_ORIGINS = os.environ.get("MEMOS_CORS_ORIGINS", "http://localhost:*")
```
Note: The glob pattern `http://localhost:*` is not standard. Use a comma-separated list of explicit origins or a regex. A safer default:
```python
_DEFAULT_CORS = "http://localhost:8000,http://localhost:8100,http://localhost:8200,http://127.0.0.1:8000,http://127.0.0.1:8100,http://127.0.0.1:8200"
_CORS_ALLOWED_ORIGINS = os.environ.get("MEMOS_CORS_ORIGINS", _DEFAULT_CORS)
```

### SEC-11: Simplify hmac.compare_digest
```python
# auth.py:87-92 — current:
def validate(self, key: str) -> bool:
    if not self._hashed_keys:
        return True
    hashed = self._hash_key(key)
    return hmac.compare_digest(hashed, hashed in self._hashed_keys and hashed or "")

# Fixed — iterate keys with constant-time comparison:
def validate(self, key: str) -> bool:
    if not self._hashed_keys:
        return True
    hashed = self._hash_key(key)
    return any(hmac.compare_digest(hashed, stored) for stored in self._hashed_keys)
```
The current expression `hashed in self._hashed_keys and hashed or ""` is a short-circuit that resolves to either `hashed` (if found) or `""` (if not), making `compare_digest` compare `hashed` with itself when the key exists. The `any()` pattern is clearer and genuinely timing-safe across all stored keys.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `body: dict` in FastAPI | Pydantic v2 model as parameter type | FastAPI 0.100+ / Pydantic v2 | Auto-validation, 422 errors, OpenAPI schema generation |
| Manual CORS headers | `CORSMiddleware` from Starlette | Starlette 0.14+ | Handles preflight, credentials, expose headers correctly |
| Sliding-window rate limit | Token bucket (already in ratelimit.py) | N/A | Smoother burst handling, per-endpoint rules |

## Open Questions

1. **CORS origin format for MCP**
   - What we know: MCP routes set CORS headers manually. REST API does not use CORSMiddleware.
   - What's unclear: Should both MCP and REST share the same CORS config, or can MCP be more restrictive?
   - Recommendation: Use the same `MEMOS_CORS_ORIGINS` env var for both. Default to localhost origins.

2. **Pydantic validation error format backward compatibility**
   - What we know: Current API returns `{"status": "error", "message": "..."}`. Pydantic returns `{"detail": [...]}`.
   - What's unclear: Are there external clients depending on the current error format?
   - Recommendation: Add a custom `RequestValidationError` handler to maintain the `{"status": "error", ...}` format.

3. **SEC-10 sanitization migration path**
   - What we know: `MEMOS_ENFORCE_SANITIZATION` env var exists in API layer. `sanitize` param exists in core.
   - What's unclear: Whether any deployments rely on the API-layer env var independently of core config.
   - Recommendation: Keep reading the env var but delegate the decision to `MemOS.sanitize`. Log a deprecation warning if the env var is set.

## Project Constraints (from CLAUDE.md)

- ES Modules only (N/A -- Python project)
- TypeScript strict (N/A -- Python project)
- Async/await everywhere, no raw `.then()` chains (N/A -- Python project)
- **Testing:** Vitest / Vue Test Utils specified for frontend; this phase is backend Python -- use `pytest`
- **Dependencies:** Ask before adding new dependency. This phase adds ZERO new dependencies.
- **Code style:** One responsibility per function, max ~40 lines per function
- **Safety:** Never push to main directly; suggest branch + PR
- **Workflow:** Plan first, implement, test, typecheck, lint
- Run single test file: `pytest tests/test_file.py` (adapt from Vitest pattern)
- A feature is not done until it has at least one test

## Sources

### Primary (HIGH confidence)
- Direct code analysis of `src/memos/api/auth.py`, `ratelimit.py`, `__init__.py`, `schemas.py`, `routes/knowledge.py`, `routes/admin.py`, `routes/memory.py`, `mcp_server.py`, `config.py`, `commands_system.py`
- `.planning/CONCERNS.md` -- pre-existing security audit
- `.planning/REQUIREMENTS.md` -- requirement definitions

### Secondary (MEDIUM confidence)
- FastAPI documentation patterns for Pydantic model injection (well-established, stable API)
- Python `logging.Filter` documentation (stdlib, stable)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all fixes use existing code
- Architecture: HIGH -- patterns are well-established FastAPI/Pydantic conventions
- Pitfalls: HIGH -- identified from direct code reading, not speculation

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (stable domain, no rapidly moving targets)
