# Claude Code + MemOS MCP Integration

Connect Claude Code to MemOS for persistent memory across sessions. Your agent remembers past decisions, preferences, and project context.

## Prerequisites

```bash
pip install memos-agent
memos serve --port 8100
```

## Step 1: Configure MCP server

Add this to `~/.claude.json`:

```json
{
  "mcpServers": {
    "memos": { "type": "http", "url": "http://localhost:8100/mcp" }
  }
}
```

Stdio transport alternative:

```json
{
  "mcpServers": {
    "memos": { "command": "memos", "args": ["mcp-stdio"] }
  }
}
```

## Step 2: Verify connection

Call `memory_stats` to confirm the server is reachable:

```
Tool: memory_stats
```

Expected response:

```
Total memories: 47
Total tags: 18
Avg relevance: 0.712
Decay candidates: 3
```

## Step 3: Store and recall

Save a decision during a session:

```
Tool: memory_save
Args: {
  "content": "Use ChromaDB as the default vector backend, not JSON. JSON is only for dev/testing.",
  "tags": ["project:memos", "architecture", "decision"],
  "importance": 0.85
}
```

Response: `Saved [a3f1b2c4] Use ChromaDB as the default vector backend, not JSON. JSON is only for d...`

Search for it later:

```
Tool: memory_search
Args: {
  "query": "which storage backend should I use?",
  "tags": ["project:memos"],
  "top_k": 3
}
```

Response:

```
[0.891] Use ChromaDB as the default vector backend, not JSON. JSON is only for dev/testing. [project:memos, architecture, decision] (importance=0.85)
```

## Step 4: Session start with wake_up

At the start of every session, call `memory_wake_up` to load your agent's identity and top memories:

```
Tool: memory_wake_up
Args: {
  "max_chars": 2000,
  "l1_top": 15
}
```

This returns a plain text block (not JSON) containing the agent's identity and highest-importance memories. Inject the returned string directly into your system prompt so the agent starts with context.

## Step 5: Targeted recall

Before starting a specific task, pull focused context:

```
Tool: memory_context_for
Args: {
  "query": "API rate limiting strategy for the memos project",
  "max_chars": 1500,
  "top": 10
}
```

This also returns a plain text string with identity plus semantic results tuned to the query. Smaller and more relevant than a full `memory_wake_up`.

## Tips

- **Namespace per project.** Use `MEMOS_NAMESPACE` env var or separate instances to isolate project memories.
- **Tag conventions.** Use `project:<name>`, `type:decision`, `type:preference` as a base pattern.
- **Importance scoring.** 0.0 to 1.0, default 0.5. Trivial facts at 0.2, decisions at 0.8, critical preferences at 0.95. Below 0.1 gets pruned.
- **Dry-run decay first.** Call `memory_decay` without `apply: true` to preview before committing.
- **Context budget.** `memory_wake_up` ~200 tokens, `memory_context_for` ~400 tokens.
