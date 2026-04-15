---
name: code-review
description: Thorough code review focused on bugs, security, performance, and maintainability. Use before committing changes.
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: review
---

## What I do
- Review diffs and PRs for bugs, security issues, race conditions, and style problems
- Check test coverage for changed code
- Verify error handling and edge cases
- Flag performance anti-patterns

## Review Checklist

### Correctness
- [ ] Logic errors, off-by-one, wrong conditionals
- [ ] Missing error handling (network calls, file I/O, DB ops)
- [ ] Type mismatches or missing null/empty checks
- [ ] Race conditions in async code

### Security
- [ ] SQL injection, XSS, command injection
- [ ] Secrets in code or logs
- [ ] Missing auth checks on API endpoints
- [ ] Unsafe deserialization

### Performance
- [ ] N+1 queries or repeated API calls in loops
- [ ] Missing pagination on list endpoints
- [ ] Unbounded memory usage (loading full datasets)
- [ ] Synchronous blocking in async context

### Maintainability
- [ ] Functions under 40 lines
- [ ] No god-classes or circular dependencies
- [ ] Proper type hints on public APIs
- [ ] Docstrings for complex logic

## How to use me
Point me at a diff, branch, or specific files. I'll give you a structured report with severity levels (🔴 critical, 🟡 warning, 🟢 suggestion).

## Commands
```bash
# Review uncommitted changes
git diff | <review>

# Review a branch vs main
git diff main...HEAD | <review>

# Review specific files
<review> src/memos/core.py src/memos/api/routes/memory.py
```
