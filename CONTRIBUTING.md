# Contributing to MemOS

Thanks for your interest in contributing to MemOS!

## Setup

```bash
git clone https://github.com/Mars375/memos
cd memos
pip install -e ".[dev,server,parquet]"
```

## Running tests

```bash
pytest -q --tb=short          # all tests
pytest tests/test_core.py     # specific module
pytest -k "test_learn"        # by name
```

## Code style

- Python 3.11+
- Type hints on all public functions
- Docstrings on modules and public APIs
- Run `ruff check .` before submitting

## Pull requests

1. Fork the repo and create a feature branch from `main`
2. Write tests for any new functionality
3. Ensure all tests pass: `pytest -q`
4. Keep PRs focused — one feature or fix per PR
5. Write a clear description of what changed and why

## Architecture

MemOS is structured in three layers (see [PRD.md](PRD.md)):

- **Capture** — `cli/`, `api/`, `mcp_server.py`, `mcp_tools/`, `ingest/`
- **Engine** — `core.py`, extracted `_*_facade.py` modules, `storage/`, `retrieval/`, `decay/`, `versioning/`, `dedup.py`
- **Knowledge Surface** — `knowledge_graph.py`, `wiki_engine.py`, `wiki_entities.py`, `wiki_models.py`, `wiki_templates.py`, `brain.py`, `web/`

Recent structural notes:

- The CLI parser now lives in `src/memos/cli/_parser/` rather than a single `cli.py` or `cli/_parser.py` monolith.
- The living wiki keeps `wiki_living.py` only as a backward-compatibility shim; new code should prefer the split wiki modules directly.
- MCP transport remains in `mcp_server.py`, while tool implementations live in `src/memos/mcp_tools/`.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
