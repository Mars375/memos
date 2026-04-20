"""Living wiki coordinator facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .wiki_engine_core import append_log, frontmatter_for_page, get_db, get_log_markdown, get_page_summary, log_action
from .wiki_engine_index import regenerate_index
from .wiki_engine_lint import lint_report as build_lint_report
from .wiki_engine_pages import create_page, get_log, list_pages, read_page, search, stats
from .wiki_engine_update import refresh_entity_page, update, update_cross_references, update_for_item
from .wiki_entities import extract_entities
from .wiki_models import LintReport, LivingPage, UpdateResult, _safe_slug


class LivingWikiEngine:
    """Entity/concept-based living wiki with incremental updates."""

    def __init__(self, memos: Any, wiki_dir: Optional[str] = None) -> None:
        self._memos = memos
        if wiki_dir:
            self._wiki_dir = Path(wiki_dir) / "living"
        else:
            persist = getattr(memos, "_persist_path", None)
            if persist:
                self._wiki_dir = Path(persist).parent / "wiki" / "living"
            else:
                self._wiki_dir = Path.home() / ".memos" / "wiki" / "living"
        self._db_path = self._wiki_dir / ".living.db"
        self._index_path = self._wiki_dir / "index.md"
        self._log_path = self._wiki_dir / "log.md"

    def _get_db(self):
        return get_db(self)

    def _safe_slug(self, name: str) -> str:
        return _safe_slug(name)

    def _get_page_summary(self, entity_name: str) -> str:
        return get_page_summary(self, entity_name)

    def _frontmatter(self, page) -> str:
        return frontmatter_for_page(page)

    def _log_action(self, db, action: str, entity: str = "", detail: str = "") -> None:
        log_action(db, action, entity, detail)

    def init(self) -> Dict[str, Any]:
        self._wiki_dir.mkdir(parents=True, exist_ok=True)
        pages_dir = self._wiki_dir / "pages"
        pages_dir.mkdir(exist_ok=True)
        db = self._get_db()
        db.close()
        if not self._index_path.exists():
            self._index_path.write_text(
                "# Living Wiki Index\n\n> Auto-generated catalog of entities and concepts.\n\n<!-- Run: memos wiki-living update -->\n",
                encoding="utf-8",
            )
        if not self._log_path.exists():
            self._log_path.write_text("# Wiki Activity Log\n\n> Append-only journal of wiki changes.\n\n", encoding="utf-8")
        return {"initialized": True, "wiki_dir": str(self._wiki_dir), "pages_dir": str(pages_dir), "db": str(self._db_path)}

    def update(self, force: bool = False) -> UpdateResult:
        return update(self, force=force)

    def update_for_item(self, item: Any) -> UpdateResult:
        return update_for_item(self, item)

    def _refresh_entity_page(self, entity: str, trigger: str | None = None, db=None) -> None:
        refresh_entity_page(self, entity, trigger=trigger, db=db)

    def _update_cross_references(self, entities: List[str], db=None) -> int:
        return update_cross_references(self, entities, db=db)

    def lint(self) -> LintReport:
        structured = self.lint_report()
        report = LintReport()
        for issue in structured["issues"]:
            issue_type = issue["type"]
            if issue_type == "orphan":
                report.orphan_pages.append(issue["page"])
            elif issue_type == "empty":
                report.empty_pages.append(issue["page"])
            elif issue_type == "contradiction":
                report.contradictions.append({"entity": issue["page"], "conflicting_terms": issue.get("conflicting_terms", [])})
            elif issue_type == "stale":
                report.stale_pages.append(issue["page"])
            elif issue_type == "missing_ref":
                report.missing_backlinks.append((issue["page"], issue.get("target", "")))
        return report

    def lint_report(self) -> Dict[str, Any]:
        self._extract_entities = extract_entities
        return build_lint_report(self)

    def generate_index(self) -> str:
        self.init()
        db = self._get_db()
        content = self._regenerate_index(db)
        db.close()
        return content

    def regenerate_index(self) -> str:
        return self.generate_index()

    def _regenerate_index(self, db) -> str:
        return regenerate_index(self, db)

    def _append_log(self, action: str, detail: str = "") -> None:
        append_log(self, action, detail)

    def get_log_markdown(self) -> str:
        return get_log_markdown(self)

    def read_page(self, entity: str) -> Optional[str]:
        return read_page(self, entity)

    def search(self, query: str) -> List[Dict[str, Any]]:
        return search(self, query)

    def get_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        return get_log(self, limit=limit)

    def create_page(self, entity: str, entity_type: str = "default", content: str = "") -> Dict[str, Any]:
        return create_page(self, entity, entity_type=entity_type, content=content)

    def list_pages(self) -> List[LivingPage]:
        return list_pages(self)

    def stats(self) -> Dict[str, Any]:
        return stats(self)
