"""Knowledge graph handle facade for MemOS."""

from __future__ import annotations

from typing import Any


class KGFacade:
    """Mixin providing lazy knowledge graph and bridge accessors."""

    @property
    def kg(self) -> Any | None:
        """Public knowledge-graph handle, if one has been initialized."""
        return self._kg_instance

    @kg.setter
    def kg(self, value: Any | None) -> None:
        self._kg_instance = value

    @property
    def kg_bridge(self) -> Any | None:
        """Public KG bridge handle, if one has been initialized."""
        return self._kg_bridge_instance

    @kg_bridge.setter
    def kg_bridge(self, value: Any | None) -> None:
        self._kg_bridge_instance = value

    def get_or_create_kg(self) -> Any:
        """Return the shared KG instance, creating it lazily when first needed."""
        if self._kg_instance is None:
            from .knowledge_graph import KnowledgeGraph

            self._kg_instance = KnowledgeGraph()
        return self._kg_instance

    def get_or_create_kg_bridge(self, kg: Any | None = None) -> Any:
        """Return the shared KG bridge, rebinding it if the KG instance changed."""
        target_kg = kg or self.get_or_create_kg()
        if self._kg_bridge_instance is None or getattr(self._kg_bridge_instance, "kg", None) is not target_kg:
            from .kg_bridge import KGBridge

            self._kg_bridge_instance = KGBridge(self, target_kg)
        return self._kg_bridge_instance
