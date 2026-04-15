# Phase 3: Documentation Polish — Execution Plan

**Phase Goal:** A developer can go from zero to a working MemOS integration in one sitting using only the README and provided examples.

## Requirements

| ID | Description | Deliverable |
|----|-------------|-------------|
| DOC-01 | README golden path walkthrough | New section in README.md |
| DOC-02 | "When to use what" recall API guide | New section in README.md |
| DOC-03 | Claude Code / MCP integration example | `examples/claude-code-mcp.md` |
| DOC-04 | OpenClaw / orchestrator integration example | `examples/openclaw-integration.md` |

## Work Units

### 03-01: README Sections (DOC-01 + DOC-02)

**Scope:** Edit `README.md` only. Add two new sections.

**DOC-01 — Golden Path** (insert after "Quick start" section, before "Python SDK"):
- Title: `## Golden path`
- Complete walkthrough: `learn → recall → context_for → wake_up → reinforce/decay`
- Each step has runnable Python code (matches actual API signatures from `core.py`, `context.py`)
- Code must work copy-paste with `from memos import MemOS` and `mem = MemOS()`
- Include inline comments explaining what each step does
- End with the decay/reinforce cycle showing how to maintain memory health
- ~60-80 lines of prose + code

**DOC-02 — When to Use What** (insert after "Python SDK", before "MCP"):
- Title: `## Which recall API should I use?`
- Table comparing 4 functions: `recall()`, `search()`/`memory_search`, `context_for()`, `recall_enriched()`
- Columns: Function, Best for, Returns, When NOT to use
- Below table, concrete 2-3 line examples for each
- Keep it tight — developers scan this, not read it

**Constraints:**
- Do NOT reorganize existing sections or change existing content
- Do NOT add new badges, images, or external links
- Match existing README style (bash/python code blocks, `##` headers, concise prose)
- Keep total README under 500 lines

### 03-02: Integration Examples (DOC-03 + DOC-04)

**Scope:** Create `examples/` directory with two new files. Do NOT edit README.

**DOC-03 — `examples/claude-code-mcp.md`:**
- Prerequisites: MemOS server running (`memos serve`)
- Step 1: Add MCP server config to `~/.claude.json` (HTTP transport)
- Step 2: Verify connection (`memory_stats` tool call)
- Step 3: Full workflow example — store memories during a conversation, recall them, reinforce important ones
- Step 4: `memory_wake_up` at session start — show the system prompt injection pattern
- Step 5: `memory_context_for` for targeted recall — show how to use it before a task
- Show actual MCP tool calls and expected responses (JSON snippets)
- Tips: namespace per project, tag conventions, importance scoring
- ~80-120 lines

**DOC-04 — `examples/openclaw-integration.md`:**
- Prerequisites: MemOS server running, OpenClaw installed
- Step 1: Add MCP config to `~/.openclaw/openclaw.json`
- Step 2: Using MemOS tools from Sisyphus/OpenClaw agents
- Step 3: Full lifecycle — wake_up at session start, learn during work, reinforce before commit
- Step 4: AGENTS.md integration — how to instruct agents to use memory tools
- Step 5: Multi-agent namespaces — agent-alice vs agent-bob isolation
- Show actual tool call patterns and JSON responses
- Tips: context window budget, when to use brain_search vs memory_search
- ~80-120 lines

**Constraints:**
- Do NOT modify any existing files
- Create `examples/` directory if it doesn't exist
- All code/config examples must be copy-paste runnable
- Use consistent formatting: `### Step N:` headers, code blocks with language tags
- Reference the actual MCP tool names from `mcp_server.py` TOOLS list

## Execution

Both work units are independent → **parallel delegation**.

## Verification (4 checks)

1. README contains "Golden path" section with `learn → recall → context_for → wake_up → reinforce` flow
2. README contains "Which recall API" section comparing 4 functions
3. `examples/claude-code-mcp.md` exists with working config + tool call examples
4. `examples/openclaw-integration.md` exists with working config + agent patterns
