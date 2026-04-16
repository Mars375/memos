"""MemOS domain constants — single source of truth for magic numbers.

All tunable numeric defaults are defined here. Modules should import
from this file rather than hardcoding values.

Sections:
    - General limits
    - Decay & reinforcement
    - Dedup
    - Consolidation
    - Compaction
    - Retrieval & embeddings
    - Knowledge Graph
    - Context stack
    - Ingest
    - Brain / entity search
    - Feedback
"""

# ── General ────────────────────────────────────────────────────────────
SECONDS_PER_DAY: int = 86_400
DEFAULT_MAX_MEMORIES: int = 10_000
DEFAULT_VECTOR_SIZE: int = 768
DEFAULT_CACHE_MAX_SIZE: int = 50_000
DEFAULT_MAX_VERSIONS_PER_ITEM: int = 100
DEFAULT_ANALYTICS_RETENTION_DAYS: int = 90

MEMORY_ID_LENGTH: int = 16  # hex chars from sha256

# ── Importance ─────────────────────────────────────────────────────────
DEFAULT_IMPORTANCE: float = 0.5
PERMANENT_IMPORTANCE_THRESHOLD: float = 0.9
IMPORTANCE_EQUALITY_TOLERANCE: float = 0.01

# ── Decay & Reinforcement ─────────────────────────────────────────────
DEFAULT_DECAY_RATE: float = 0.01
DEFAULT_REINFORCE_STRENGTH: float = 0.05
DEFAULT_ACCESS_BOOST: float = 0.05
DEFAULT_IMPORTANCE_FLOOR: float = 0.1
DEFAULT_PRUNE_THRESHOLD: float = 0.1
DEFAULT_PRUNE_MAX_AGE_DAYS: float = 90.0
DEFAULT_DECAY_MIN_AGE_DAYS: float = 7.0
HARD_MAX_AGE_DAYS: float = 365.0
IMPORTANCE_FLOOR_FACTOR: float = 0.1  # in adjusted_score

# ── Dedup ──────────────────────────────────────────────────────────────
DEFAULT_DEDUP_THRESHOLD: float = 0.95

# ── Consolidation ──────────────────────────────────────────────────────
DEFAULT_CONSOLIDATION_THRESHOLD: float = 0.75
CONSOLIDATION_RECENCY_FADE_DAYS: int = 90
MERGE_IMPORTANCE_WEIGHT: float = 0.7
MERGE_RECENCY_WEIGHT: float = 0.3
MERGE_ACCESS_COUNT_WEIGHT: float = 0.01
MERGE_RECENCY_FLOOR: float = 0.1
UNIQUE_CONTENT_RATIO_THRESHOLD: float = 0.4

# ── Compaction ─────────────────────────────────────────────────────────
DEFAULT_ARCHIVE_AGE_DAYS: float = 90.0
DEFAULT_ARCHIVE_IMPORTANCE_FLOOR: float = 0.3
DEFAULT_STALE_SCORE_THRESHOLD: float = 0.25
DEFAULT_MERGE_SIMILARITY_THRESHOLD: float = 0.6
DEFAULT_CLUSTER_MIN_SIZE: int = 3
DEFAULT_CLUSTER_MAX_SIZE: int = 20
DEFAULT_MAX_COMPACT_PER_RUN: int = 200
COMPACTION_MERGE_IMPORTANCE_BOOST: float = 0.05
CLUSTER_SUMMARY_MIN_IMPORTANCE: float = 0.3
CLUSTER_SUMMARY_IMPORTANCE_FACTOR: float = 0.7
STALE_MERGE_NOVELTY_RATIO: float = 0.3

# ── Retrieval & Embeddings ────────────────────────────────────────────
DEFAULT_SEMANTIC_WEIGHT: float = 0.6
DEFAULT_EMBED_TIMEOUT: float = 30.0
TAG_BONUS_PER_TAG: float = 0.1
TAG_BONUS_MAX: float = 0.3
IMPORTANCE_BOOST_WEIGHT: float = 0.1
RECENCY_FADE_DAYS: int = 30
RECENCY_BONUS_WEIGHT: float = 0.1
TEMPORAL_PROXIMITY_WEIGHT: float = 0.05
TEMPORAL_PROXIMITY_WINDOW: int = 3600  # 1 hour in seconds
EMBED_CACHE_MAX: int = 5_000
EMBED_CACHE_EVICT_COUNT: int = 2_500

# ── Knowledge Graph ────────────────────────────────────────────────────
KG_SHORT_ID_LENGTH: int = 8
DEFAULT_INFERENCE_MAX_DEPTH: int = 3
DEFAULT_FIND_PATHS_MAX: int = 10
DEFAULT_SHORTEST_PATH_MAX_HOPS: int = 5

# ── Brain / Entity Search ─────────────────────────────────────────────
KG_WEIGHT_EXTRACTED: float = 1.0
KG_WEIGHT_INFERRED: float = 0.85
KG_WEIGHT_AMBIGUOUS: float = 0.65
KG_WEIGHT_DEFAULT: float = 0.7
KG_DIRECT_MATCH_BONUS: float = 0.2
WIKI_ENTITY_IN_QUERY_BONUS: float = 0.15
DEFAULT_SNIPPET_WINDOW: int = 80

# ── Context Stack ──────────────────────────────────────────────────────
WAKE_UP_MAX_CHARS: int = 2_000
WAKE_UP_L1_TOP: int = 15
WAKE_UP_COMPACT_MAX_CHARS: int = 800
WAKE_UP_COMPACT_L1_TOP: int = 5
CONTEXT_FOR_MAX_CHARS: int = 1_500

# ── Ingest ─────────────────────────────────────────────────────────────
DEFAULT_MAX_CHUNK_SIZE: int = 2_000

# ── Feedback ───────────────────────────────────────────────────────────
FEEDBACK_IMPORTANCE_DELTA: float = 0.1
STATS_DECAY_THRESHOLD: float = 0.2
