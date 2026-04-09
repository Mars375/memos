"""Zero-LLM knowledge graph extraction from memory text."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable

_ENTITY = r"[A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ&./'+:-]*(?:\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ&./'+:-]*)*"
_ENTITY_RE = re.compile(rf"\b{_ENTITY}\b")
_SENTENCE_SPLIT_RE = re.compile(r"(?:[.!?]\s+|\n+)")
_NEGATION_RE = re.compile(
    r"\b(?:not|never|no|doesn't|don't|didn't|isn't|aren't|can't|cannot|won't|without|"
    r"pas|jamais|aucun|aucune|sans)\b|\bne\b.+\bpas\b|\bn['’]\w+",
    re.IGNORECASE,
)
_CONDITIONAL_RE = re.compile(
    r"\b(?:if|would|could|might|maybe|perhaps|should|si|serait|pourrait|devrait|peut-être)\b",
    re.IGNORECASE,
)
_AMBIGUOUS_HINT_RE = re.compile(
    r"\b(?:with|on|for|inside|within|sur|dans|avec|pour|team|équipe|project|projet|service|stack)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedFact:
    """A structured fact extracted from free text."""

    subject: str
    predicate: str
    object: str
    confidence: float = 0.9
    confidence_label: str = "EXTRACTED"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _PatternSpec:
    predicate: str
    regex: re.Pattern[str]
    confidence: float = 0.9
    confidence_label: str = "EXTRACTED"


class KGExtractor:
    """Extract lightweight KG triples from memory text without any LLM."""

    def __init__(self, *, project_patterns: Iterable[str] | None = None) -> None:
        self._project_patterns = [re.compile(p, re.IGNORECASE) for p in project_patterns or []]
        self._patterns = self._build_patterns()

    def extract(self, content: str) -> list[ExtractedFact]:
        """Extract KG facts from free text."""
        facts: list[ExtractedFact] = []
        seen: set[tuple[str, str, str, str]] = set()

        for sentence in self._split_sentences(content):
            if not sentence:
                continue
            if self._should_skip(sentence):
                continue

            matched = False
            for spec in self._patterns:
                for match in spec.regex.finditer(sentence):
                    subject = self._clean_entity(match.group("subject"))
                    obj = self._clean_entity(match.group("object"))
                    if not self._is_valid_fact(subject, obj):
                        continue
                    fact = ExtractedFact(
                        subject=subject,
                        predicate=spec.predicate,
                        object=obj,
                        confidence=spec.confidence,
                        confidence_label=spec.confidence_label,
                    )
                    key = (fact.subject.casefold(), fact.predicate, fact.object.casefold(), fact.confidence_label)
                    if key not in seen:
                        seen.add(key)
                        facts.append(fact)
                    matched = True

            if matched:
                continue

            for fact in self._extract_ambiguous(sentence):
                key = (fact.subject.casefold(), fact.predicate, fact.object.casefold(), fact.confidence_label)
                if key not in seen:
                    seen.add(key)
                    facts.append(fact)

        return facts

    def detect_entities(self, content: str) -> list[str]:
        """Detect simple entity-like spans from text."""
        entities: list[str] = []
        seen: set[str] = set()

        for match in _ENTITY_RE.findall(content):
            entity = self._clean_entity(match)
            if not entity:
                continue
            key = entity.casefold()
            if key in seen:
                continue
            seen.add(key)
            entities.append(entity)

        for regex in self._project_patterns:
            for match in regex.finditer(content):
                entity = self._clean_entity(match.group(0))
                if not entity:
                    continue
                key = entity.casefold()
                if key not in seen:
                    seen.add(key)
                    entities.append(entity)

        return entities

    def _extract_ambiguous(self, sentence: str) -> list[ExtractedFact]:
        if not _AMBIGUOUS_HINT_RE.search(sentence):
            return []
        entities = self.detect_entities(sentence)
        if len(entities) < 2:
            return []
        subject, obj = entities[0], entities[1]
        if not self._is_valid_fact(subject, obj):
            return []
        return [
            ExtractedFact(
                subject=subject,
                predicate="related_to",
                object=obj,
                confidence=0.35,
                confidence_label="AMBIGUOUS",
            )
        ]

    @staticmethod
    def _split_sentences(content: str) -> list[str]:
        parts = _SENTENCE_SPLIT_RE.split(content or "")
        return [" ".join(part.split()).strip(" ,;:()[]{}") for part in parts if part and part.strip()]

    @staticmethod
    def _clean_entity(value: str) -> str:
        entity = " ".join((value or "").split()).strip(" ,.;:()[]{}\"'")
        return entity

    @staticmethod
    def _is_valid_fact(subject: str, obj: str) -> bool:
        if not subject or not obj:
            return False
        if len(subject) < 2 or len(obj) < 2:
            return False
        if subject.casefold() == obj.casefold():
            return False
        return True

    @staticmethod
    def _should_skip(sentence: str) -> bool:
        return bool(_NEGATION_RE.search(sentence) or _CONDITIONAL_RE.search(sentence))

    @staticmethod
    def _build_patterns() -> list[_PatternSpec]:
        return [
            _PatternSpec(
                "works_at",
                re.compile(
                    rf"(?P<subject>{_ENTITY})\s+(?i:(?:works?|worked|working)\s+(?:at|for))\s+(?P<object>{_ENTITY})",
                ),
                confidence=0.97,
            ),
            _PatternSpec(
                "works_at",
                re.compile(
                    rf"(?P<subject>{_ENTITY})\s+(?i:(?:travaille|boss[e]?|bosse)\s+(?:chez|pour))\s+(?P<object>{_ENTITY})",
                ),
                confidence=0.97,
            ),
            _PatternSpec(
                "is",
                re.compile(
                    rf"(?P<subject>{_ENTITY})\s+(?i:(?:is|was)(?:\s+(?:an?|the))?)\s+(?P<object>{_ENTITY})",
                ),
                confidence=0.9,
            ),
            _PatternSpec(
                "is",
                re.compile(
                    rf"(?P<subject>{_ENTITY})\s+(?i:est(?:\s+(?:un|une|le|la|l['’]))?)\s+(?P<object>{_ENTITY})",
                ),
                confidence=0.9,
            ),
            _PatternSpec(
                "uses",
                re.compile(
                    rf"(?P<subject>{_ENTITY})\s+(?i:(?:uses|used|using|runs on|built with))\s+(?P<object>{_ENTITY})",
                ),
                confidence=0.93,
            ),
            _PatternSpec(
                "uses",
                re.compile(
                    rf"(?P<subject>{_ENTITY})\s+(?i:(?:utilise|utilisent|tourne sur|construit avec))\s+(?P<object>{_ENTITY})",
                ),
                confidence=0.93,
            ),
            _PatternSpec(
                "deployed_to",
                re.compile(
                    rf"(?P<subject>{_ENTITY})\s+(?i:(?:deployed|deploys|shipped)\s+(?:to|on|into))\s+(?P<object>{_ENTITY})",
                ),
                confidence=0.94,
            ),
            _PatternSpec(
                "deployed_to",
                re.compile(
                    rf"(?P<subject>{_ENTITY})\s+(?i:(?:a\s+été\s+)?déploy(?:é|ée)?\s+(?:sur|dans|vers))\s+(?P<object>{_ENTITY})",
                ),
                confidence=0.94,
            ),
            _PatternSpec(
                "fixed",
                re.compile(
                    rf"(?P<subject>{_ENTITY})\s+(?i:(?:fixed|resolved|patched))\s+(?P<object>{_ENTITY})",
                ),
                confidence=0.92,
            ),
            _PatternSpec(
                "fixed",
                re.compile(
                    rf"(?P<subject>{_ENTITY})\s+(?i:(?:a\s+)?(?:corrigé|réparé|résolu))\s+(?P<object>{_ENTITY})",
                ),
                confidence=0.92,
            ),
        ]
