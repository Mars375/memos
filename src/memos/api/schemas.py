"""Pydantic request models for MemOS API endpoints."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

# ── Memory ───────────────────────────────────────────────────


class LearnRequest(BaseModel):
    """Store a single memory."""

    content: str = Field(..., min_length=1, max_length=10000, description="Memory content")
    tags: Optional[list[str]] = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: Optional[dict[str, Any]] = None

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t) for t in v]
        return None


class LearnExtractRequest(LearnRequest):
    """Learn a memory and extract KG facts."""

    pass


class BatchLearnRequest(BaseModel):
    """Batch store multiple memories."""

    items: list[LearnRequest] = Field(..., min_length=1, max_length=1000)
    continue_on_error: bool = True


class TagFilter(BaseModel):
    """Structured tag filter for recall."""

    include: list[str] = Field(default_factory=list)
    require: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    mode: str = "ANY"


class ImportanceFilter(BaseModel):
    """Importance range filter."""

    min: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RecallRequest(BaseModel):
    """Semantic recall / search."""

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=200, alias="top_k")
    tags: Optional[Any] = None  # list[str] or TagFilter dict — resolved in route
    filter_tags: Optional[list[str]] = None
    importance: ImportanceFilter = Field(default_factory=ImportanceFilter)
    retrieval_mode: str = Field(default="semantic", pattern="^(semantic|keyword|hybrid)$")
    explain: bool = False
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    created_after: Optional[Any] = None  # ISO string or float
    created_before: Optional[Any] = None
    filter_after: Optional[Any] = None
    filter_before: Optional[Any] = None
    rerank: bool = False

    model_config = {"populate_by_name": True}

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v


class PruneRequest(BaseModel):
    """Decay-based cleanup."""

    threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    max_age_days: float = Field(default=90.0, ge=0.0)
    dry_run: bool = True


class TagRenameRequest(BaseModel):
    """Rename a tag across all memories."""

    old: str = Field(..., min_length=1)
    new: str = Field(..., min_length=1)


class TagDeleteRequest(BaseModel):
    """Delete a tag from all memories."""

    tag: str = Field(..., min_length=1)


class ConsolidateRequest(BaseModel):
    """Merge similar memories."""

    similarity_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    merge_content: bool = False
    dry_run: bool = True
    async_: Optional[bool] = Field(default=False, alias="async")

    model_config = {"populate_by_name": True}


class RollbackRequest(BaseModel):
    """Roll back a memory to a previous version."""

    version: int = Field(..., ge=1)


class VersioningGCRequest(BaseModel):
    """Garbage-collect old versions."""

    max_age_days: float = Field(default=90.0, ge=0.0)
    keep_latest: int = Field(default=3, ge=1)


class FeedbackRequest(BaseModel):
    """Record relevance feedback."""

    item_id: str = Field(..., min_length=1)
    feedback: str = Field(..., min_length=1)
    query: str = ""
    score_at_recall: float = Field(default=0.0, ge=0.0, le=1.0)
    agent_id: str = ""


class DedupCheckRequest(BaseModel):
    """Check if content is a duplicate."""

    content: str = Field(..., min_length=1)
    threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class DedupScanRequest(BaseModel):
    """Scan all memories for duplicates."""

    fix: bool = False
    threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SyncCheckRequest(BaseModel):
    """Check sync conflicts."""

    envelope: dict[str, Any] = Field(..., description="Memory envelope to check")


class SyncApplyRequest(BaseModel):
    """Apply synced memories."""

    envelope: dict[str, Any] = Field(..., description="Memory envelope to apply")
    strategy: str = "merge"
    dry_run: bool = False

    @field_validator("strategy")
    @classmethod
    def _validate_strategy(cls, v: str) -> str:
        valid = {"local_wins", "remote_wins", "merge", "manual"}
        if v not in valid:
            raise ValueError(f"Invalid strategy. Must be one of: {sorted(valid)}")
        return v


class CompressRequest(BaseModel):
    """Compress memories."""

    threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    dry_run: bool = True


class DecayRunRequest(BaseModel):
    """Run importance decay cycle."""

    min_age_days: Optional[float] = Field(default=None, ge=0.0)
    floor: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    dry_run: bool = True


class ReinforceRequest(BaseModel):
    """Boost a memory's importance."""

    strength: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# ── Knowledge Graph ──────────────────────────────────────────


class FactRequest(BaseModel):
    """Add a temporal triple to the knowledge graph."""

    subject: str = Field(..., min_length=1)
    predicate: str = Field(..., min_length=1)
    object: str = Field(..., min_length=1)
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence_label: str = "EXTRACTED"
    source: Optional[str] = None


class InferRequest(BaseModel):
    """Infer transitive facts."""

    predicate: str = Field(..., min_length=1)
    inferred_predicate: Optional[str] = None
    max_depth: int = Field(default=3, ge=1, le=10)


# ── Brain Search ─────────────────────────────────────────────


class BrainSearchRequest(BaseModel):
    """Unified search across memories, wiki, and KG."""

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    tags: Optional[list[str]] = None
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    retrieval_mode: str = Field(default="hybrid", pattern="^(semantic|keyword|hybrid)$")
    max_context_chars: int = Field(default=2000, ge=100, le=50000)


# ── Palace ───────────────────────────────────────────────────


class PalaceCreateWingRequest(BaseModel):
    """Create a palace wing."""

    name: str = Field(..., min_length=1)
    description: str = ""


class PalaceCreateRoomRequest(BaseModel):
    """Create a palace room."""

    wing: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""


class PalaceAssignRequest(BaseModel):
    """Assign a memory to a palace room."""

    memory_id: str = Field(..., min_length=1)
    wing: str = Field(..., min_length=1)
    room: Optional[str] = None


# ── Context ──────────────────────────────────────────────────


class ContextIdentityRequest(BaseModel):
    """Set the identity context."""

    content: str = Field(..., min_length=1)


# ── Admin / Ingest ──────────────────────────────────────────


class IngestURLRequest(BaseModel):
    """Fetch and ingest a URL."""

    url: str = Field(..., min_length=1)
    tags: Optional[list[str]] = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    max_chunk: int = Field(default=2000, ge=100, le=50000)
    dry_run: bool = False


class MineConversationRequest(BaseModel):
    """Mine a conversation transcript."""

    text: Optional[str] = Field(default=None, alias="text")
    content: Optional[str] = None
    path: Optional[str] = None
    per_speaker: bool = True
    namespace_prefix: str = "conv"
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.6, ge=0.0, le=1.0)
    dry_run: bool = False

    model_config = {"populate_by_name": True}


# ── Namespace ACL ────────────────────────────────────────────


class ACLGrantRequest(BaseModel):
    """Grant namespace access to an agent."""

    agent_id: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    granted_by: str = ""
    expires_at: Optional[str] = None


class ACLRevokeRequest(BaseModel):
    """Revoke namespace access."""

    agent_id: str = Field(..., min_length=1)


# ── Sharing ──────────────────────────────────────────────────


class ShareOfferRequest(BaseModel):
    """Offer to share memories with another agent."""

    target_agent: str = Field(..., min_length=1)
    scope: str = "items"
    scope_key: str = ""
    permission: str = "read"
    expires_at: Optional[str] = None

    @field_validator("scope")
    @classmethod
    def _validate_scope(cls, v: str) -> str:
        valid = {"items", "tag", "namespace", "all"}
        if v not in valid:
            raise ValueError(f"Invalid scope. Must be one of: {sorted(valid)}")
        return v

    @field_validator("permission")
    @classmethod
    def _validate_permission(cls, v: str) -> str:
        valid = {"read", "write", "admin"}
        if v not in valid:
            raise ValueError(f"Invalid permission. Must be one of: {sorted(valid)}")
        return v


class ShareImportRequest(BaseModel):
    """Import shared memories from an envelope."""

    envelope: dict[str, Any] = Field(..., description="Memory envelope to import")
