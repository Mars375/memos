"""MCP Pre/Post hooks — auto-capture and context injection (P4).

Hooks run before or after every MCP tool dispatch, allowing you to:

- **Pre-hooks**: inject context or modify args before a tool call
- **Post-hooks**: auto-capture facts or augment results after a tool call

Built-in hooks
--------------
``hook_inject_wake_up``
    Prepends a compact wake-up context block to ``memory_search`` results
    so the agent always has L0+L1 context injected alongside search results.

``hook_auto_capture_kg``
    After ``memory_save``, tries to extract simple subject→predicate→object
    triples from the saved content and records them in the KG.

Usage::

    from memos.mcp_hooks import MCPHookRegistry, hook_inject_wake_up

    registry = MCPHookRegistry()
    registry.register_post("memory_save", hook_auto_capture_kg)
    registry.register_pre("memory_search", hook_inject_wake_up)

    # In _dispatch:
    result = _dispatch_core(memos, tool, args)
    result = registry.run_post(tool, args, result, memos)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class MCPHookRegistry:
    """Registry of pre/post hooks keyed by tool name.

    Pre-hooks may return a dict to short-circuit the tool call (the dict
    becomes the response), or ``None`` to let the call proceed normally.

    Post-hooks receive the tool result and may return a modified version.
    Exceptions in hooks are silently swallowed so the main call always succeeds.
    """

    def __init__(self) -> None:
        self._pre: dict[str, list[Callable]] = {}
        self._post: dict[str, list[Callable]] = {}

    def register_pre(self, tool: str, fn: Callable) -> None:
        """Register *fn* as a pre-hook for *tool*."""
        self._pre.setdefault(tool, []).append(fn)

    def register_post(self, tool: str, fn: Callable) -> None:
        """Register *fn* as a post-hook for *tool*."""
        self._post.setdefault(tool, []).append(fn)

    def unregister(self, tool: str) -> None:
        """Remove all hooks for *tool*."""
        self._pre.pop(tool, None)
        self._post.pop(tool, None)

    def run_pre(self, tool: str, args: dict, memos: Any) -> dict | None:
        """Run all pre-hooks for *tool*.

        Returns the first non-None response from any hook (short-circuit),
        or None if all hooks pass through.
        """
        for fn in self._pre.get(tool, []):
            try:
                result = fn(tool, args, memos)
                if result is not None:
                    return result
            except Exception:
                logger.warning("Pre-hook failed for tool %s", tool, exc_info=True)
                pass
        return None

    def run_post(self, tool: str, args: dict, result: dict, memos: Any) -> dict:
        """Run all post-hooks for *tool*, returning (possibly modified) result."""
        for fn in self._post.get(tool, []):
            try:
                new_result = fn(tool, args, result, memos)
                if new_result is not None:
                    result = new_result
            except Exception:
                logger.warning("Post-hook failed for tool %s", tool, exc_info=True)
                pass
        return result

    @property
    def registered_tools(self) -> set[str]:
        """Set of tool names that have at least one hook registered."""
        return set(self._pre) | set(self._post)


# ---------------------------------------------------------------------------
# Built-in hooks
# ---------------------------------------------------------------------------


def hook_inject_wake_up(tool: str, args: dict, memos: Any) -> None:
    """PRE-hook: inject compact wake-up context before memory_search.

    This hook does not short-circuit (returns None), but it is kept as a
    pre-hook stub.  The actual injection happens in hook_prepend_context_post,
    which runs *after* the search so it can combine context + results.
    """
    return None


def hook_prepend_context(tool: str, args: dict, result: dict, memos: Any) -> dict:
    """POST-hook: prepend compact wake-up context to memory_search results.

    Prepends [CONTEXT] block to the result text so the agent sees both
    its standing context and the search results in one response.
    """
    try:
        from .context import ContextStack

        cs = ContextStack(memos)
        context = cs.wake_up(compact=True)
        if not context.strip():
            return result

        current_text = ""
        if isinstance(result, dict) and result.get("content"):
            for block in result["content"]:
                if isinstance(block, dict) and block.get("type") == "text":
                    current_text = block.get("text", "")
                    break

        combined = f"[CONTEXT]\n{context}\n\n[SEARCH RESULTS]\n{current_text}"
        return {
            "content": [{"type": "text", "text": combined}],
            "isError": result.get("isError", False),
        }
    except Exception:
        return result


def hook_auto_capture_kg(tool: str, args: dict, result: dict, memos: Any) -> dict:
    """POST-hook: extract simple KG facts from memory_save content.

    Looks for patterns like "X is-a Y", "X works-at Y", "X owns Y", etc.
    using a small set of regex patterns.  Extracted facts are stored in the
    KG with confidence_label="EXTRACTED".

    Does not modify the result dict — purely a side-effect hook.
    """
    content = args.get("content", "")
    if not content or len(content) < 10:
        return result

    try:
        kg = getattr(memos, "kg", None) or getattr(memos, "_kg", None)
        if kg is None:
            return result

        _extract_and_store_facts(content, kg)
    except Exception:
        logger.warning("KG auto-capture hook failed", exc_info=True)
        pass
    return result


# ---------------------------------------------------------------------------
# KG extraction helpers
# ---------------------------------------------------------------------------

# Simple verb patterns: (subject) VERB (object)
_EXTRACTION_PATTERNS: list[tuple[str, str]] = [
    # "Alice is a developer"
    (r"\b([A-Z][a-zA-Z]+)\s+is(?:\s+a|\s+an)?\s+([A-Z][a-zA-Z]+)\b", "is-a"),
    # "Alice works at CompanyX" / "Alice works_at CompanyX"
    (r"\b([A-Z][a-zA-Z]+)\s+works[\s_]at\s+([A-Z][a-zA-Z]+)\b", "works-at"),
    # "Alice leads TeamA"
    (r"\b([A-Z][a-zA-Z]+)\s+leads\s+([A-Z][a-zA-Z]+)\b", "leads"),
    # "Alice manages Bob"
    (r"\b([A-Z][a-zA-Z]+)\s+manages\s+([A-Z][a-zA-Z]+)\b", "manages"),
    # "Alice owns ProjectX"
    (r"\b([A-Z][a-zA-Z]+)\s+owns\s+([A-Z][a-zA-Z]+)\b", "owns"),
    # "ProjectX depends on ProjectY"
    (r"\b([A-Z][a-zA-Z]+)\s+depends\s+on\s+([A-Z][a-zA-Z]+)\b", "depends-on"),
    # "Alice uses Tool"
    (r"\b([A-Z][a-zA-Z]+)\s+uses\s+([A-Z][a-zA-Z]+)\b", "uses"),
]


def _extract_and_store_facts(content: str, kg: Any) -> list[str]:
    """Extract triples from *content* and add them to *kg*.

    Returns list of fact IDs created.
    """
    fact_ids: list[str] = []
    for pattern, predicate in _EXTRACTION_PATTERNS:
        for m in re.finditer(pattern, content):
            subject, obj = m.group(1), m.group(2)
            if subject == obj:
                continue
            try:
                fid = kg.add_fact(
                    subject,
                    predicate,
                    obj,
                    confidence=0.7,
                    confidence_label="EXTRACTED",
                    source="mcp-hook:auto-capture",
                )
                fact_ids.append(fid)
            except Exception:
                logger.warning("Failed to store extracted fact %s %s %s", subject, predicate, obj, exc_info=True)
                pass
    return fact_ids


# ---------------------------------------------------------------------------
# Agent wing auto-creation
# ---------------------------------------------------------------------------


def hook_ensure_agent_wing(tool: str, args: dict, memos: Any) -> None:
    """PRE-hook: auto-create a palace wing for the calling agent's namespace.

    When an agent calls ``memory_save`` (learn) or ``memory_search`` (recall)
    via MCP, this hook ensures a wing named ``agent-{namespace}`` exists in
    the palace index.  The namespace is extracted from ``args["namespace"]``
    (or defaults to ``"default"``).

    This hook does **not** short-circuit — it always returns ``None`` so the
    tool call proceeds normally.  Wing creation is idempotent.
    """
    namespace = args.get("namespace") or "default"
    wing_name = f"agent-{namespace}"

    palace = getattr(memos, "_palace", None)
    if palace is None:
        return None

    try:
        palace.create_wing(wing_name, description=f"Auto-created wing for agent namespace '{namespace}'")
    except Exception:
        logger.warning("Failed to auto-create agent wing %s", wing_name, exc_info=True)

    return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_default_registry(
    auto_context: bool = False,
    auto_kg: bool = False,
    auto_agent_wing: bool = False,
) -> MCPHookRegistry:
    """Create a registry with optional built-in hooks enabled.

    Parameters
    ----------
    auto_context:
        If True, prepend wake-up context to every memory_search result.
    auto_kg:
        If True, auto-extract KG facts after every memory_save.
    auto_agent_wing:
        If True, auto-create a palace wing for the agent namespace on
        every ``memory_save`` / ``memory_search`` call.
    """
    registry = MCPHookRegistry()
    if auto_context:
        registry.register_post("memory_search", hook_prepend_context)
    if auto_kg:
        registry.register_post("memory_save", hook_auto_capture_kg)
    if auto_agent_wing:
        registry.register_pre("memory_save", hook_ensure_agent_wing)
        registry.register_pre("memory_search", hook_ensure_agent_wing)
    return registry
