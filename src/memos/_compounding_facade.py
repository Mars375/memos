"""Compounding ingest facade for Living Wiki integration."""

from __future__ import annotations

from typing import Any, Optional


class CompoundingFacade:
    """Mixin providing compounding-ingest controls for the MemOS nucleus."""

    def enable_compounding_ingest(self, wiki_dir: Optional[str] = None) -> None:
        """Enable compounding ingest: auto-update wiki pages on every ``learn()`` call.

        When enabled, each new memory triggers a lightweight
        :meth:`~memos.wiki_living.LivingWikiEngine.update_for_item` call
        that creates or updates entity pages for the memory's entities and tags.

        Parameters
        ----------
        wiki_dir:
            Optional path to the wiki directory.  Defaults to ``~/.memos/wiki``.
        """
        from .wiki_living import LivingWikiEngine

        self._living_wiki = LivingWikiEngine(self, wiki_dir=wiki_dir)
        self._wiki_auto_update = True

    def disable_compounding_ingest(self) -> None:
        """Disable compounding ingest."""
        self._living_wiki = None
        self._wiki_auto_update = False

    @property
    def compounding_ingest(self) -> bool:
        """Whether compounding ingest is currently enabled."""
        return self._wiki_auto_update

    @property
    def wiki_auto_update(self) -> bool:
        """Whether wiki auto-update is enabled on every learn() call."""
        return self._wiki_auto_update

    @wiki_auto_update.setter
    def wiki_auto_update(self, value: bool) -> None:
        """Enable or disable wiki auto-update."""
        self._wiki_auto_update = value

    @property
    def living_wiki(self) -> Any:
        """The LivingWikiEngine instance, or None if not initialized."""
        return self._living_wiki

    @property
    def _compounding_wiki(self) -> Any:
        """Backward-compatible alias for older compounding-ingest integrations."""
        return self._living_wiki

    @_compounding_wiki.setter
    def _compounding_wiki(self, value: Any) -> None:
        self._living_wiki = value
