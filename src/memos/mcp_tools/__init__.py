"""MCP tool registry — imports all domain modules and exports the aggregated TOOLS list and dispatch function."""

from __future__ import annotations

# Import domain modules to trigger registration
from ._enriched import *  # noqa: F401 F403
from ._knowledge_graph import *  # noqa: F401 F403
from ._memory import *  # noqa: F401 F403
from ._palace import *  # noqa: F401 F403
from ._registry import dispatch, get_all_schemas
from ._sync import *  # noqa: F401 F403
from ._wiki import *  # noqa: F401 F403

TOOLS = get_all_schemas()

__all__ = ["TOOLS", "dispatch"]
