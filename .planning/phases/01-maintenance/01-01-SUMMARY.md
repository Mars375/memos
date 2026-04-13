---
phase: 01-maintenance
plan: "01"
subsystem: infra
tags: [version, docker, ci, maintenance]
dependency_graph:
  requires: []
  provides: [version-2.2.0-synced, docker-images-pinned, log-limits, ci-matrix-313]
  affects: [pypi-release, docker-deploy, ci]
tech_stack:
  added: []
  patterns: [pinned-docker-images, json-file-logging, ci-matrix-expansion]
key_files:
  created: []
  modified:
    - pyproject.toml
    - docker-compose.yml
    - .github/workflows/test.yml
decisions:
  - "ghcr.io/mars375/memos:latest retained as-is — project's own image, tag managed externally"
  - "chromadb/chroma pinned to 1.5.7 (latest stable at execution time)"
  - "qdrant/qdrant pinned to v1.17.1 (latest stable at execution time)"
metrics:
  duration: "~2 minutes"
  completed: "2026-04-13T18:11:32Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Phase 01 Plan 01: Maintenance Hardening Summary

**One-liner:** Version drift fixed (pyproject 1.0.0 -> 2.2.0), Docker images pinned with json-file log limits on all 5 services, CI matrix expanded to Python 3.11/3.12/3.13.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Sync version and harden Docker Compose | cdeef39 | pyproject.toml, docker-compose.yml |
| 2 | Expand CI matrix to Python 3.13 | 38fc7ec | .github/workflows/test.yml |

## What Was Done

### Task 1 — Version sync + Docker hardening

- `pyproject.toml`: bumped `version` from `"1.0.0"` to `"2.2.0"` — now matches `__init__.__version__`
- `docker-compose.yml`: replaced `chromadb/chroma:latest` with `chromadb/chroma:1.5.7`
- `docker-compose.yml`: replaced `qdrant/qdrant:latest` with `qdrant/qdrant:v1.17.1`
- `docker-compose.yml`: added `logging: driver: json-file / max-size: "10m" / max-file: "3"` to all 5 services (`memos-standalone`, `memos`, `chroma`, `memos-qdrant`, `qdrant`)

### Task 2 — CI matrix expansion

- `.github/workflows/test.yml`: changed `["3.11", "3.12"]` to `["3.11", "3.12", "3.13"]` in the `test` job matrix
- Lint job untouched (still runs on 3.11)

## Verification Results

```
version = "2.2.0"          # pyproject.toml ✓
__version__ = "2.2.0"     # src/memos/__init__.py ✓
:latest                     # only ghcr.io/mars375/memos (3 lines) ✓
max-size count: 5           # all 5 services have log limits ✓
3.13 in CI matrix           # ✓
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- pyproject.toml modified: FOUND (version = "2.2.0")
- docker-compose.yml modified: FOUND (chromadb/chroma:1.5.7, qdrant/qdrant:v1.17.1, 5x max-size)
- .github/workflows/test.yml modified: FOUND (3.13 in matrix)
- Commit cdeef39: FOUND
- Commit 38fc7ec: FOUND
