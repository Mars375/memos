"""Memory sanitizer — prevents prompt injection through stored memories."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SanitizeIssue:
    """A detected sanitization issue."""
    rule: str
    severity: Severity
    description: str
    match: str


# Patterns that could indicate prompt injection in memory content
_INJECTION_PATTERNS = [
    (r"(?i)ignore\s+(all\s+)?previous\s+instructions", Severity.CRITICAL,
     "Ignore-previous-instructions pattern"),
    (r"(?i)you\s+are\s+now\s+(a|an)\s+\w+", Severity.HIGH,
     "Role override pattern"),
    (r"(?i)system\s*:\s*", Severity.HIGH,
     "System message injection"),
    (r"(?i)(forget|discard|erase|delete|wipe)\s+(all\s+)?(your|the)?\s*(memory|memories|instructions|context|history)",
     Severity.CRITICAL, "Memory wipe instruction"),
    (r"<\|im_start\|>|<\|im_end\|>", Severity.HIGH,
     "ChatML token injection"),
    (r"(?i)^(human|assistant|system)\s*:", Severity.MEDIUM,
     "Role prefix injection"),
    (r"\[INST\]|\[/INST\]", Severity.HIGH,
     "Llama instruction token"),
    (r"(?i)api[_\s-]*key[^a-z]{0,5}(?:is\s+)?(sk-[a-z0-9]+|\S{8,})", Severity.MEDIUM,
     "API key in memory (credential leak)"),
    (r"(?i)password\s*[=:]\s*\S+", Severity.MEDIUM,
     "Password in memory (credential leak)"),
    (r"(?i)secret[_-]?key\s*[=:]\s*\S+", Severity.MEDIUM,
     "Secret key in memory (credential leak)"),
    (r"(?i)token\s*[=:]\s*['\"]?\w{20,}", Severity.MEDIUM,
     "Long token value (possible credential)"),
    (r"(?i)\bssh[-_]\w+\s*[=:]", Severity.LOW,
     "SSH credential pattern"),
    (r"(?i)private[-_]key\s*[=:]", Severity.MEDIUM,
     "Private key reference"),
]

# Maximum memory length to prevent token flooding
MAX_MEMORY_LENGTH = 10_000


class MemorySanitizer:
    """Validates memory content for safety before storage."""

    @classmethod
    def check(cls, content: str) -> list[SanitizeIssue]:
        """Check content for injection patterns and safety issues.
        
        Returns:
            List of issues found. Empty list means content is safe.
        """
        issues = []

        # Check length
        if len(content) > MAX_MEMORY_LENGTH:
            issues.append(SanitizeIssue(
                rule="max_length",
                severity=Severity.MEDIUM,
                description=f"Memory exceeds {MAX_MEMORY_LENGTH} chars ({len(content)})",
                match=content[:50],
            ))

        # Check injection patterns
        for pattern, severity, description in _INJECTION_PATTERNS:
            match = re.search(pattern, content)
            if match:
                issues.append(SanitizeIssue(
                    rule=f"pattern_{pattern[:20]}",
                    severity=severity,
                    description=description,
                    match=match.group(),
                ))

        return issues

    @classmethod
    def is_safe(cls, content: str) -> bool:
        """Quick check if content passes all sanitization rules."""
        issues = cls.check(content)
        return not issues

    @classmethod
    def strip_credentials(cls, content: str) -> str:
        """Remove credential-like patterns from content."""
        patterns = [
            (r"(?i)api[_-]?key\s*[=:]\s*\S+", "[API_KEY_REDACTED]"),
            (r"(?i)password\s*[=:]\s*\S+", "[PASSWORD_REDACTED]"),
            (r"(?i)secret[_-]?key\s*[=:]\s*\S+", "[SECRET_REDACTED]"),
            (r"(?i)token\s*[=:]\s*['\"]?\w{20,}", "[TOKEN_REDACTED]"),
            (r"(?i)private[-_]key\s*[=:]\s*\S+", "[PRIVATE_KEY_REDACTED]"),
        ]
        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)
        return content
