"""Auto-tagger — zero-LLM memory type classification.

Classifies memories into semantic categories using regex patterns.
Inspired by mempalace: 96.6% accuracy without LLM extraction.

Categories:
    decision, preference, milestone, problem, emotional, fact, action, question
"""

from __future__ import annotations

import re
from typing import Optional


# ── Type tag definitions ──────────────────────────────────────────────

_TAG_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "decision": [
        # French
        re.compile(r"\bj'ai d[ée]cid[ée]\b", re.I),
        re.compile(r"\bon a choisi\b", re.I),
        re.compile(r"\ble choix (?:est|a [ée]t[ée])\b", re.I),
        re.compile(r"\bnous avons d[ée]cid[ée]e?\b", re.I),
        re.compile(r"\bd[ée]cision\s*(?:prisee?|finale|importante)\b", re.I),
        re.compile(r"\bvalid[ée]e?\b", re.I),
        re.compile(r"\bretenu(?:e)?\s+(?:pour|comme)\b", re.I),
        # English
        re.compile(r"\bwe decided\b", re.I),
        re.compile(r"\bI decided\b", re.I),
        re.compile(r"\bthe (?:choice|decision) (?:is|was)\b", re.I),
        re.compile(r"\bgoing with\b", re.I),
        re.compile(r"\bpicked\s+\w+\s+(?:over|instead)\b", re.I),
        re.compile(r"\bagreed (?:to|on|that)\b", re.I),
        re.compile(r"\bruled (?:out|that)\b", re.I),
        re.compile(r"\bsettled on\b", re.I),
    ],
    "preference": [
        # French
        re.compile(r"\bj'aime\b", re.I),
        re.compile(r"\bje pr[éeè]f[éeè]re?\b", re.I),
        re.compile(r"\bmon pr[ée]f[ée]r[ée]\b", re.I),
        re.compile(r"\bje n'aime pas\b", re.I),
        re.compile(r"\bje d[ée]teste\b", re.I),
        re.compile(r"\bme pla[îi]t\b", re.I),
        re.compile(r"\bme convient\b", re.I),
        # English
        re.compile(r"\bI prefer\b", re.I),
        re.compile(r"\bmy favorite\b", re.I),
        re.compile(r"\bI (?:really )?like\b", re.I),
        re.compile(r"\bI (?:don't|do not) like\b", re.I),
        re.compile(r"\bI hate\b", re.I),
        re.compile(r"\bI love\b", re.I),
        re.compile(r"\bcan't stand\b", re.I),
        re.compile(r"\bbest (?:option|choice|approach)\b", re.I),
    ],
    "milestone": [
        # French
        re.compile(r"\btermin[ée]e?\b", re.I),
        re.compile(r"\blivr[ée]e?\b", re.I),
        re.compile(r"\bmis en production\b", re.I),
        re.compile(r"\bd[ée]ploy[ée]e?\b", re.I),
        re.compile(r"\bachev[ée]e?\b", re.I),
        re.compile(r"\bfini\b", re.I),
        re.compile(r"\baccompli(?:e)?\b", re.I),
        # English
        re.compile(r"\bdeployed\b", re.I),
        re.compile(r"\bshipped\b", re.I),
        re.compile(r"\bcompleted\b", re.I),
        re.compile(r"\blaunched\b", re.I),
        re.compile(r"\breleased\b", re.I),
        re.compile(r"\bfinished\b", re.I),
        re.compile(r"\bdone\s+(?:with|by)\b", re.I),
        re.compile(r"\bmilestone\b", re.I),
        re.compile(r"\bwent live\b", re.I),
    ],
    "problem": [
        # French
        re.compile(r"\bbug\b", re.I),
        re.compile(r"\berreur\b", re.I),
        re.compile(r"\bbloqu[ée]e?\b", re.I),
        re.compile(r"\bplantage\b", re.I),
        re.compile(r"\bprobl[éeè]me\b", re.I),
        re.compile(r"\bcass[ée]e?\b", re.I),
        re.compile(r"\bne marche pas\b", re.I),
        re.compile(r"\bne fonctionne pas\b", re.I),
        re.compile(r"\bfix[ée]e?\b", re.I),
        re.compile(r"\bincident\b", re.I),
        # English
        re.compile(r"\berror\b", re.I),
        re.compile(r"\bbroken\b", re.I),
        re.compile(r"\bcrash(?:ed)?\b", re.I),
        re.compile(r"\bissue\b", re.I),
        re.compile(r"\bfail(?:ed|ure|ing)?\b", re.I),
        re.compile(r"\bnot working\b", re.I),
        re.compile(r"\bregression\b", re.I),
    ],
    "emotional": [
        # French
        re.compile(r"\bfrustrant(?:e)?\b", re.I),
        re.compile(r"\b(?:je suis|il est|elle est|on est|nous sommes)\s+content(?:e)?\b", re.I),
        re.compile(r"\bexcit[ée]e?(?:e)?\b", re.I),
        re.compile(r"\bfier(?:e)?\b", re.I),
        re.compile(r"\bagac[ée](?:e)?\b", re.I),
        re.compile(r"\b[ée]nnerv[ée]e?(?:e)?\b", re.I),
        re.compile(r"\bd[ée]çu(?:e)?\b", re.I),
        re.compile(r"\binquiet(?:e|tude)?\b", re.I),
        re.compile(r"\bsuper content\b", re.I),
        # English
        re.compile(r"\bfrustrat(?:ed|ing)\b", re.I),
        re.compile(r"\bexcited\b", re.I),
        re.compile(r"\bproud\b", re.I),
        re.compile(r"\bannoyed\b", re.I),
        re.compile(r"\bdisappointed\b", re.I),
        re.compile(r"\bworried\b", re.I),
        re.compile(r"\bhappy\b", re.I),
        re.compile(r"\bsad\b", re.I),
        re.compile(r"\bthrilled\b", re.I),
        re.compile(r"\bgrateful\b", re.I),
        re.compile(r"\bstressed\b", re.I),
    ],
    "fact": [
        # French
        re.compile(r"\bc'est (?:un |une )?(?:fait|constat)\b", re.I),
        re.compile(r"\bil (?:y a |existe )\b", re.I),
        re.compile(r"\b(?:le|la|les) (?:total|nombre|chiffre) (?:est|s'[ée]l[èe]ve(?:nt)? [àa])\b", re.I),
        # English
        re.compile(r"\b(?:it|this) (?:is|has) (?:a |an )?(?:fact|total|known)\b", re.I),
        re.compile(r"\bthere (?:is|are) \d+\b", re.I),
        re.compile(r"\bstatistics? (?:show|say|indicate)\b", re.I),
        re.compile(r"\baccording to\b", re.I),
    ],
    "action": [
        # French
        re.compile(r"\b(?:il faut|on doit|je dois|nous devons)\b", re.I),
        re.compile(r"\b(?:[àa] faire|todo|action)\b", re.I),
        re.compile(r"\bprochaine [ée]tape\b", re.I),
        re.compile(r"\bplan d'action\b", re.I),
        # English
        re.compile(r"\b(?:need to|must|should|have to|gotta)\b", re.I),
        re.compile(r"\btodo\b", re.I),
        re.compile(r"\baction item\b", re.I),
        re.compile(r"\bnext step\b", re.I),
        re.compile(r"\blet's\b", re.I),
        re.compile(r"\bgoing to\b", re.I),
    ],
    "question": [
        re.compile(r"\?"),
        re.compile(r"\bhow (?:to|do|does|can|should)\b", re.I),
        re.compile(r"\bwhat (?:is|are|was|if)\b", re.I),
        re.compile(r"\bwhy\b", re.I),
        re.compile(r"\bwhere (?:is|are|can)\b", re.I),
        re.compile(r"\bwho (?:is|are|did)\b", re.I),
        re.compile(r"\bcomment\b.*\?", re.I),
        re.compile(r"\bpourquoi\b", re.I),
    ],
}

# All valid type tags
TYPE_TAGS = frozenset(_TAG_PATTERNS.keys())


class AutoTagger:
    """Classify memory content into type tags using regex patterns.

    Usage:
        tagger = AutoTagger()
        tags = tagger.tag("We decided to use PostgreSQL for the new project.")
        # -> ["decision"]

        tags = tagger.tag("The build is broken and I'm frustrated!")
        # -> ["problem", "emotional"]
    """

    def __init__(self, custom_patterns: Optional[dict[str, list[str]]] = None) -> None:
        """Initialize the tagger with optional custom patterns.

        Args:
            custom_patterns: Dict of tag -> list of regex strings to add.
        """
        self._patterns: dict[str, list[re.Pattern[str]]] = {}
        for tag, patterns in _TAG_PATTERNS.items():
            self._patterns[tag] = list(patterns)

        if custom_patterns:
            for tag, regex_strs in custom_patterns.items():
                if tag not in self._patterns:
                    self._patterns[tag] = []
                for regex_str in regex_strs:
                    self._patterns[tag].append(re.compile(regex_str, re.I))

    def tag(self, content: str) -> list[str]:
        """Classify content and return matching type tags.

        Args:
            content: The memory content to classify.

        Returns:
            List of matching type tags (may be empty).
        """
        if not content or not content.strip():
            return []

        results: list[str] = []
        for tag, patterns in self._patterns.items():
            for pattern in patterns:
                if pattern.search(content):
                    results.append(tag)
                    break  # One match per tag is enough

        return results

    def tag_detailed(self, content: str) -> dict[str, list[str]]:
        """Classify content and return detailed match info.

        Returns:
            Dict mapping tag -> list of matched pattern strings.
        """
        if not content or not content.strip():
            return {}

        results: dict[str, list[str]] = {}
        for tag, patterns in self._patterns.items():
            matches = []
            for pattern in patterns:
                m = pattern.search(content)
                if m:
                    matches.append(m.group(0))
            if matches:
                results[tag] = matches

        return results

    def has_type_tags(self, tags: list[str]) -> bool:
        """Check if a tag list already contains type tags.

        Args:
            tags: Existing tags on a memory.

        Returns:
            True if any tag is a known type tag.
        """
        return bool(set(tags) & TYPE_TAGS)

    def auto_tag(self, content: str, existing_tags: Optional[list[str]] = None) -> list[str]:
        """Auto-classify and return tags to append (excluding already present).

        Args:
            content: The memory content to classify.
            existing_tags: Tags already on the memory.

        Returns:
            List of new type tags to add.
        """
        if existing_tags and self.has_type_tags(existing_tags):
            return []  # Don't override existing type tags

        detected = self.tag(content)
        if not existing_tags:
            return detected

        existing_set = set(existing_tags)
        return [t for t in detected if t not in existing_set]
