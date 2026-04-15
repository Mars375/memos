# OpenClaw + MemOS Integration

Wire MemOS into OpenClaw agent sessions so every agent starts with memory, reinforces what matters, and forgets what doesn't.

## Prerequisites

```bash
memos serve --port 8100
# Verify: curl http://localhost:8100/health
```

## Step 1: Configure MCP

Add this to `~/.openclaw/openclaw.json`:

```json
{
  "mcp": {
    "servers": {
      "memos": { "type": "http", "url": "http://localhost:8100/mcp" }
    }
  }
}
```

## Step 2: Agent memory lifecycle

The full cycle for a single session:

**Start.** Call `memory_wake_up` at session start. The response is a plain text string with agent identity and top-importance memories. Inject it into the system prompt.

```
Tool: memory_wake_up
Args: { "max_chars": 2000, "l1_top": 15 }
```

**During work.** Save decisions, discoveries, and corrections as they happen:

```
Tool: memory_save
Args: {
  "content": "The frontend uses force-graph for the canvas, not D3 directly. Chart.js for analytics.",
  "tags": ["project:memos", "frontend", "architecture"],
  "importance": 0.7
}
```

Response: `Saved [e7d2a9f1] The frontend uses force-graph for the canvas, not D3 directly. Chart.js ...`

**Before commit.** Reinforce memories that proved useful during the session:

```
Tool: memory_reinforce
Args: {
  "memory_id": "e7d2a9f1",
  "strength": 0.05
}
```

Response: `Reinforced e7d2a9f1 (importance 0.70 -> 0.75)`

## Step 3: AGENTS.md integration

Add memory instructions to your project's `AGENTS.md` so agents know when to use each tool:

```markdown
## Memory Protocol

- **Session start:** Call `memory_wake_up` and inject the result into your context.
- **Before coding tasks:** Call `memory_context_for` with a query describing the task.
- **After decisions:** Call `memory_save` with tags and importance.
- **Before commit:** Call `memory_reinforce` on any memory you recalled and found useful.
- **Weekly:** Run `memory_decay` with `apply: true` to prune stale memories.
```

## Step 4: Multi-agent namespaces

When multiple agents work on the same MemOS instance, isolate their memories with namespaces:

```bash
MEMOS_NAMESPACE=agent-alice memos serve --port 8101
MEMOS_NAMESPACE=agent-bob memos serve --port 8102
```

Each agent's MCP config points to its own port. Memories stay isolated.

If you want shared memories instead, use a single instance and differentiate with tags:

```
Tool: memory_save
Args: {
  "content": "Refactored the CLI parser into three focused modules.",
  "tags": ["agent:alice", "project:memos", "refactor"],
  "importance": 0.6
}
```

Then search with tag filters:

```
Tool: memory_search
Args: {
  "query": "CLI refactoring changes",
  "require_tags": ["agent:alice"],
  "top_k": 5
}
```

## Tips

- **Context budget.** `memory_wake_up` ~200 tokens, `memory_context_for` ~400 tokens. Both return plain text.
- **`brain_search` vs `memory_search`.** Use `memory_search` for ranked results. Use `brain_search` for a fused view across memories, wiki, and KG facts.
- **Decay scheduling.** Run `memory_decay` with `apply: true` weekly. Always dry-run first.
- **Recall enriched.** Use `memory_recall_enriched` for memories plus KG facts in one call. Good for entity-centric queries.
- **Forget by tag.** Call `memory_forget` with a `tag` to bulk-delete outdated project memories.
