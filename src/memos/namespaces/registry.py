"""Persistent namespace metadata registry."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path


_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/-]{0,127}$")


@dataclass
class NamespaceRecord:
    """Metadata associated with a namespace."""

    name: str
    description: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "NamespaceRecord":
        return cls(
            name=str(data.get("name", "")).strip(),
            description=str(data.get("description", "") or "").strip(),
            created_at=float(data.get("created_at", 0.0) or 0.0),
            updated_at=float(data.get("updated_at", 0.0) or 0.0),
        )


class NamespaceRegistry:
    """Track namespace metadata independently from memory contents."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path).expanduser() if path else None
        self._records: dict[str, NamespaceRecord] = {}
        self._load()

    @staticmethod
    def validate_name(name: str) -> str:
        candidate = (name or "").strip()
        if not candidate:
            raise ValueError("namespace name is required")
        if not _NAMESPACE_RE.fullmatch(candidate):
            raise ValueError(
                "invalid namespace name, expected letters/digits plus : . _ / -"
            )
        return candidate

    def _load(self) -> None:
        if self._path is None or not self._path.is_file():
            self._records = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._records = {}
            return
        records: dict[str, NamespaceRecord] = {}
        if isinstance(raw, dict):
            for name, data in raw.items():
                if isinstance(data, dict):
                    record = NamespaceRecord.from_dict({"name": name, **data})
                    if record.name:
                        records[record.name] = record
        self._records = records

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            name: {
                "description": record.description,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
            for name, record in sorted(self._records.items())
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def register(self, name: str, description: str | None = None) -> dict[str, object]:
        namespace = self.validate_name(name)
        now = time.time()
        existing = self._records.get(namespace)
        if existing is None:
            existing = NamespaceRecord(
                name=namespace,
                description=(description or "").strip(),
                created_at=now,
                updated_at=now,
            )
            self._records[namespace] = existing
        else:
            if description is not None:
                existing.description = description.strip()
            existing.updated_at = now
        self._save()
        return existing.to_dict()

    def touch(self, name: str) -> dict[str, object]:
        return self.register(name, description=None)

    def get(self, name: str) -> dict[str, object] | None:
        namespace = (name or "").strip()
        record = self._records.get(namespace)
        return record.to_dict() if record else None

    def delete(self, name: str) -> bool:
        namespace = (name or "").strip()
        removed = self._records.pop(namespace, None)
        if removed is not None:
            self._save()
            return True
        return False

    def list(self) -> list[dict[str, object]]:
        return [record.to_dict() for _, record in sorted(self._records.items())]
