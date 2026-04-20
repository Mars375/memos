"""Living Wiki — backward-compatible re-exports.

This module has been split into focused sub-modules:
- wiki_entities: entity extraction (STOP_WORDS, extract_entities)
- wiki_templates: page templates (_frontmatter, _PAGE_TEMPLATES)
- wiki_models: data classes (LivingPage, LintReport, UpdateResult)
- wiki_engine: LivingWikiEngine class

All symbols remain importable from this module for backward compatibility.
"""

from .wiki_engine import LivingWikiEngine  # noqa: F401
from .wiki_entities import _STOPWORDS, STOP_WORDS, extract_entities  # noqa: F401
from .wiki_models import LintReport, LivingPage, UpdateResult  # noqa: F401
from .wiki_templates import _PAGE_TEMPLATES, _frontmatter  # noqa: F401
