"""MemOS Context Stack — Multi-layer contextual retrieval (P7).

Inspired by MemPalace, the ContextStack provides tiered context retrieval:

    L0 (~100 tokens) — Identity: who the agent is, always injected
    L1 (~700 tokens) — Top-N memories by importance (wake-up session priming)
    L2 (~300 tokens) — Scoped recall filtered by tags
    L3             — Full semantic search, unconstrained

Usage::

    from memos.context import ContextStack
    cs = ContextStack(memos)
    print(cs.wake_up())

"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .core import MemOS
    from .models import RecallResult


class ContextStack:
    """Multi-layer context stack for LLM agent session priming.

    Parameters
    ----------
    memos:
        A fully constructed :class:`~memos.core.MemOS` instance.
    identity_path:
        Path to the agent identity file.  Supports ``~`` expansion.
        Defaults to ``~/.memos/identity.txt``.
    """

    def __init__(
        self,
        memos: "MemOS",
        identity_path: str = "~/.memos/identity.txt",
    ) -> None:
        self._memos = memos
        self._identity_path = Path(identity_path).expanduser()

    # ------------------------------------------------------------------ #
    # L0 — Identity                                                        #
    # ------------------------------------------------------------------ #

    def set_identity(self, content: str) -> None:
        """Write *content* to the identity file.

        Creates parent directories if they do not exist.
        """
        self._identity_path.parent.mkdir(parents=True, exist_ok=True)
        self._identity_path.write_text(content, encoding="utf-8")

    def get_identity(self) -> str:
        """Read and return the identity file content.

        Returns an empty string if the file does not exist.
        """
        if not self._identity_path.exists():
            return ""
        return self._identity_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ #
    # Wake-up — L0 + L1                                                   #
    # ------------------------------------------------------------------ #

    def wake_up(
        self,
        max_chars: int = 2000,
        l1_top: int = 15,
        include_stats: bool = True,
    ) -> str:
        """Return L0 + L1 as a string ready to inject into a system prompt.

        The output format is LLM-friendly plain text:

        .. code-block:: text

            === IDENTITY ===
            <identity content>

            === MEMORY CONTEXT (N memories) ===
            [0.92] Python async best practices (tags: python, async)
            [0.87] Docker multi-stage builds (tags: devops)
            ...

            === STATS ===
            Total: 142 memories | Tags: 23 | Decay candidates: 3

        Parameters
        ----------
        max_chars:
            Hard upper bound on the total character count of the output.
            The result is truncated if it would exceed this limit.
        l1_top:
            Number of top-importance memories to include in L1.
        include_stats:
            Whether to append a ``=== STATS ===`` section.
        """
        parts: list[str] = []

        # L0 — Identity
        identity = self.get_identity()
        identity_section = "=== IDENTITY ===\n"
        if identity.strip():
            identity_section += identity.rstrip()
        parts.append(identity_section)

        # L1 — Top memories by importance
        all_items = self._memos._store.list_all(namespace=self._memos.namespace)
        # Sort by importance descending, then by access_count for tie-breaking
        all_items_sorted = sorted(
            all_items,
            key=lambda x: (x.importance, x.access_count),
            reverse=True,
        )
        top_items = all_items_sorted[:l1_top]

        mem_lines: list[str] = []
        for item in top_items:
            tags_str = f" (tags: {', '.join(item.tags)})" if item.tags else ""
            mem_lines.append(f"[{item.importance:.2f}] {item.content}{tags_str}")

        n = len(top_items)
        memory_section = f"=== MEMORY CONTEXT ({n} memories) ===\n"
        if mem_lines:
            memory_section += "\n".join(mem_lines)
        parts.append(memory_section)

        # Stats section
        if include_stats:
            s = self._memos.stats()
            stats_section = (
                f"=== STATS ===\n"
                f"Total: {s.total_memories} memories | "
                f"Tags: {s.total_tags} | "
                f"Decay candidates: {s.decay_candidates}"
            )
            parts.append(stats_section)

        output = "\n\n".join(parts)

        # Strict max_chars truncation
        if max_chars > 0 and len(output) > max_chars:
            output = output[:max_chars]

        return output

    # ------------------------------------------------------------------ #
    # L2 — Scoped recall by tags                                          #
    # ------------------------------------------------------------------ #

    def recall_l2(
        self,
        query: str,
        tags: Optional[List[str]] = None,
        top: int = 10,
    ) -> "List[RecallResult]":
        """L2: recall filtered by specific tags.

        Parameters
        ----------
        query:
            The search query string.
        tags:
            Optional list of tags to scope the search.  If ``None``, behaves
            like an unfiltered recall.
        top:
            Maximum number of results to return.
        """
        return self._memos.recall(query, top=top, filter_tags=tags)

    # ------------------------------------------------------------------ #
    # L3 — Full semantic search                                           #
    # ------------------------------------------------------------------ #

    def recall_l3(
        self,
        query: str,
        top: int = 50,
    ) -> "List[RecallResult]":
        """L3: full semantic search with no tag constraints.

        Parameters
        ----------
        query:
            The search query string.
        top:
            Maximum number of results to return.
        """
        return self._memos.recall(query, top=top)

    # ------------------------------------------------------------------ #
    # context_for — L0 + L3 for a specific query                         #
    # ------------------------------------------------------------------ #

    def context_for(
        self,
        query: str,
        max_chars: int = 1500,
        top: int = 10,
    ) -> str:
        """Return the most relevant context for *query*.

        Combines L0 (identity) with the top L3 semantic search results.
        Useful for augmenting a single LLM call with relevant memories.

        Parameters
        ----------
        query:
            The query to retrieve context for.
        max_chars:
            Hard upper bound on total character count.
        top:
            Number of semantic search results to include.
        """
        parts: list[str] = []

        # L0
        identity = self.get_identity()
        if identity.strip():
            parts.append("=== IDENTITY ===\n" + identity.rstrip())

        # L3 semantic results
        results = self.recall_l3(query, top=top)
        if results:
            lines: list[str] = []
            for r in results:
                tags_str = f" (tags: {', '.join(r.item.tags)})" if r.item.tags else ""
                lines.append(f"[{r.score:.2f}] {r.item.content}{tags_str}")
            parts.append(
                f"=== RELEVANT MEMORIES ({len(results)} results for: {query!r}) ===\n"
                + "\n".join(lines)
            )

        output = "\n\n".join(parts)

        if max_chars > 0 and len(output) > max_chars:
            output = output[:max_chars]

        return output
