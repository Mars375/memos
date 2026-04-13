"""Skills-as-markdown export (P10) — package MemOS workflows as reusable agent skills.

Generates Markdown skill files compatible with:
- **Claude Code** slash commands (``~/.claude/commands/*.md``)
- **Cursor** rules / custom prompts
- **Generic** markdown prompts for any LLM agent

Each skill file contains a ready-to-use prompt that calls ``memos`` CLI
commands or MCP tools, pre-configured with sensible defaults from the
current MemOS instance (namespace, backend, etc.).

Usage::

    from memos.skills import SkillsExporter
    exporter = SkillsExporter(memos)
    result = exporter.export("~/.claude/commands/", format="claude-code")
    print(result)  # SkillsExportResult(written=8, skipped=0, output_dir=...)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SKILL_TEMPLATES: dict[str, str] = {
    "memos-recall": """\
# /memos-recall

Recall relevant memories from MemOS for the current task.

## Usage
Call this before starting any task to surface relevant past knowledge.

```bash
memos recall "$QUERY" --top 10
```

Replace `$QUERY` with the topic or question you need context for.

## When to use
- Beginning a new task or conversation
- When you need historical context about a topic
- Before making an architectural decision
""",
    "memos-wake-up": """\
# /memos-wake-up

Inject MemOS identity and top memories into the current session context.

## Usage
Run at the start of each session to prime the agent with standing context.

```bash
memos wake-up --compact
```

For full context (more tokens):
```bash
memos wake-up --top 20
```

## Output
Returns [ID] identity, [MEM] top-N memory snippets, and [STATS] summary.
""",
    "memos-learn": """\
# /memos-learn

Store a new memory in MemOS from the current conversation.

## Usage
```bash
memos learn "$CONTENT" --tags "$TAGS" --importance 0.7
```

## Guidelines
- `--importance 0.9+` for decisions, key facts, architectural choices
- `--importance 0.5-0.7` for context, observations, notes
- `--importance 0.1-0.4` for ephemeral / low-value notes
- Always add at least one meaningful tag

## Examples
```bash
memos learn "Chose PostgreSQL over SQLite for production — needs concurrent writes" --tags "database,decision" --importance 0.9
memos learn "Alice is the lead for the authentication service" --tags "team,auth" --importance 0.75
```
""",
    "memos-kg-add": """\
# /memos-kg-add

Add a knowledge graph fact extracted from the conversation.

## Usage
```bash
memos kg-add "$SUBJECT" "$PREDICATE" "$OBJECT" --label EXTRACTED
```

## Common predicates
`works-at`, `leads`, `manages`, `owns`, `uses`, `depends-on`, `is-a`,
`part-of`, `integrates-with`, `replaces`, `successor-of`

## Examples
```bash
memos kg-add "Alice" "leads" "TeamA"
memos kg-add "ServiceA" "depends-on" "ServiceB"
memos kg-add "PostgreSQL" "is-a" "database"
```
""",
    "memos-kg-lint": """\
# /memos-kg-lint

Audit the knowledge graph for quality issues.

## Usage
```bash
memos kg-lint --min-facts 2
```

## What it checks
- **Contradictions**: same subject+predicate pointing to multiple objects
- **Orphans**: entities appearing in only one triple (dangling references)
- **Sparse**: entities with fewer than `--min-facts` active facts

## When to use
- Before a knowledge-intensive task
- After bulk-importing conversation history
- As part of a weekly knowledge hygiene routine
""",
    "memos-mine": """\
# /memos-mine

Import conversation history, notes, or project files into MemOS memory.

## Usage
```bash
# Auto-detect format
memos mine "$PATH"

# Import Claude conversation export
memos mine-conversation "$PATH" --format claude

# Import a directory of notes
memos mine "$DIRECTORY" --tags "notes,project"
```

## Supported formats
- Claude JSON export (`.json`)
- ChatGPT export (`.json`)
- Slack JSONL (`.jsonl`)
- Discord export (`.json`)
- Telegram export (`result.json`)
- OpenClaw session logs (`.json`, `.jsonl`)
- Markdown / text files
- Code files (`.py`, `.ts`, `.go`, etc.)
""",
    "memos-stale": """\
# /memos-stale

Check which previously-mined sources have changed and need re-importing.

## Usage
```bash
# Show only changed/missing sources
memos mine-stale --only-stale

# Show all sources with their status
memos mine-stale
```

## Status codes
- `~` **changed** — file on disk differs from the cached hash
- `✗` **missing** — file was deleted or moved
- `✓` **fresh** — file is unchanged since last mine

## Re-mining changed sources
```bash
memos mine --update "$PATH"
```
""",
    "memos-stats": """\
# /memos-stats

Show memory store statistics including token usage estimates.

## Usage
```bash
memos stats
```

## Output includes
- Total memories and tags
- Average importance and relevance
- Decay candidates (memories that should be pruned)
- **Token estimate** — approximate token count of all memories
- Prunable and expired token counts

## Maintenance hints
```bash
memos decay        # prune low-importance memories
memos prune --expired  # remove TTL-expired memories
memos consolidate  # merge similar memories
```
""",
}


@dataclass
class SkillsExportResult:
    output_dir: str
    written: int = 0
    skipped: int = 0
    skills: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return f"SkillsExportResult(written={self.written}, skipped={self.skipped}, output_dir={self.output_dir!r})"


class SkillsExporter:
    """Export MemOS workflows as reusable agent skill files.

    Parameters
    ----------
    memos:
        Optional :class:`~memos.core.MemOS` instance.  Used to inject
        instance-specific defaults (namespace, backend) into skill templates.
    """

    def __init__(self, memos: Any = None) -> None:
        self._memos = memos

    def export(
        self,
        output_dir: str,
        format: str = "claude-code",
        skills: list[str] | None = None,
        overwrite: bool = False,
    ) -> SkillsExportResult:
        """Write skill files to *output_dir*.

        Parameters
        ----------
        output_dir:
            Target directory.  Created if it does not exist.
        format:
            Output format.  Currently ``"claude-code"`` (markdown with
            YAML-free front-matter compatible with Claude Code slash commands)
            or ``"generic"`` (plain markdown).
        skills:
            Optional list of skill names to export.  Defaults to all built-in
            skills.
        overwrite:
            If False (default), skip files that already exist.

        Returns
        -------
        :class:`SkillsExportResult`
        """
        out = Path(output_dir).expanduser()
        out.mkdir(parents=True, exist_ok=True)

        to_export = skills or list(_SKILL_TEMPLATES.keys())
        result = SkillsExportResult(output_dir=str(out))

        for skill_name in to_export:
            template = _SKILL_TEMPLATES.get(skill_name)
            if template is None:
                continue

            content = self._render(template, skill_name, format)
            filename = f"{skill_name}.md"
            dest = out / filename

            if dest.exists() and not overwrite:
                result.skipped += 1
                continue

            dest.write_text(content, encoding="utf-8")
            result.written += 1
            result.skills.append(skill_name)

        return result

    def list_skills(self) -> list[str]:
        """Return the names of all available built-in skills."""
        return list(_SKILL_TEMPLATES.keys())

    def _render(self, template: str, skill_name: str, format: str) -> str:
        """Render a skill template, injecting instance context if available."""
        content = template

        # Inject namespace if set
        ns = getattr(self._memos, "_namespace", "") if self._memos else ""
        if ns:
            content = content.replace(
                "memos recall",
                f"memos --namespace {ns} recall",
            )

        if format == "claude-code":
            # Claude Code slash commands use the H1 as the command name
            # and support $ARGUMENTS placeholder
            content = re.sub(
                r"\$QUERY\b",
                "$ARGUMENTS",
                content,
            )

        return content
