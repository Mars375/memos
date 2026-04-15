---
name: monolith-split
description: Decompose monolithic Python files into focused, well-structured modules. Analyzes dependencies, proposes split plan, and implements refactoring.
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: refactoring
---

## What I do
- Identify logical groupings within a monolithic file
- Propose a concrete split plan with file names and responsibilities
- Implement the split while preserving all tests
- Update all imports across the codebase

## Split Methodology

### Phase 1: Analyze
1. Map all classes and functions (with line counts)
2. Identify logical groupings by responsibility
3. Map cross-references between groups
4. Check test coverage for the file

### Phase 2: Plan
Produce a concrete plan in this format:
```
monolith.py (N lines)
├── module_a.py (~X lines) — Responsibility A
│   ├── class FooBar
│   └── function baz()
├── module_b.py (~Y lines) — Responsibility B
│   ├── class Qux
│   └── helpers
└── monolith.py (~Z lines) — Re-exports for backward compatibility
    └── from .module_a import *  # deprecated shim
```

### Phase 3: Implement
1. Create new module files with the split code
2. Update `__init__.py` for package exports
3. Fix ALL imports across the entire codebase (src/ AND tests/)
4. Add backward-compatibility re-exports in original file
5. Run full test suite — ALL tests must pass

### Phase 4: Verify
```bash
python -m pytest tests/ -q          # All tests pass
ruff check src/ tests/               # No lint errors
grep -r "from monolith import" src/  # No stale imports
```

## Rules
1. **Never break backward compatibility** — always add re-export shims
2. **One responsibility per module** — if a module does X and Y, split it
3. **Keep circular deps out** — if A imports B and B imports A, one of them needs an interface/protocol
4. **Preserve ALL tests** — if tests break, the split is wrong
5. **Target under 400 lines per file** — anything over 500 is a smell

## Current Monoliths in MemOS (by priority)
1. `core.py` (1909L) — God class, needs decomposition
2. `cli/_parser.py` (1171L) — Argparse monolith
3. `wiki_living.py` (1080L) — Wiki engine
4. `cli/commands_memory.py` (1036L) — Memory CLI
5. `mcp_server.py` (851L) — MCP endpoints

## When to use me
- When a file exceeds 500 lines
- When a class has more than 5 responsibilities
- When `git blame` shows the file changes constantly (high churn = needs split)
- During code review when you spot a monolith
