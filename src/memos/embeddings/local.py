"""Local embedder using sentence-transformers — no Ollama/external service needed.

Supports two backends:
- **sentence-transformers** (default): Full-featured, requires ``torch`` or
  ``onnxruntime`` as backend. Best quality.
- **onnxruntime** fallback: Lighter weight, no torch dependency.

The embedder is lazy — the model is loaded on first use, not at import time.
This means ``pip install memos`` works without ``sentence-transformers``; the
local embedder simply raises a helpful error if used without its dependency.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Default model — small, fast, good quality for English + multilingual
_DEFAULT_MODEL = "all-MiniLM-L6-v2"


class LocalEmbedder:
    """Embedding provider backed by sentence-transformers (local, no API calls).

    Usage::

        embedder = LocalEmbedder(model="all-MiniLM-L6-v2")
        vec = embedder.encode("Hello world")  # -> list[float] of dim 384

    The model is downloaded on first use (cached by sentence-transformers in
    ``~/.cache/torch/sentence_transformers/``). Subsequent calls are fast.

    If ``sentence-transformers`` is not installed, ``encode()`` returns ``None``
    and a warning is logged — graceful degradation.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        *,
        device: Optional[str] = None,
        normalize: bool = True,
    ) -> None:
        self._model_name = model
        self._device = device
        self._normalize = normalize
        self._model: object | None = None  # SentenceTransformer instance
        self._dim: int | None = None
        # Allow overriding via environment
        if not model:
            self._model_name = os.environ.get("MEMOS_LOCAL_MODEL", _DEFAULT_MODEL)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int | None:
        """Return embedding dimension after model is loaded, else None."""
        return self._dim

    def _load_model(self) -> bool:
        """Lazy-load the sentence-transformers model. Returns True on success."""
        if self._model is not None:
            return True

        try:
            from sentence_transformers import SentenceTransformer

            kwargs: dict = {}
            if self._device:
                kwargs["device"] = self._device

            logger.info("Loading local embedding model '%s' (first use)…", self._model_name)
            self._model = SentenceTransformer(self._model_name, **kwargs)
            self._dim = self._model.get_sentence_embedding_dimension()
            logger.info("Model loaded — dimension=%d", self._dim)
            return True

        except ImportError:
            logger.warning(
                "sentence-transformers is not installed. "
                "Install it with: pip install 'memos-agent[local]' "
                "or pip install sentence-transformers"
            )
            return False
        except Exception as exc:
            logger.error("Failed to load local embedding model '%s': %s", self._model_name, exc)
            return False

    def encode(self, text: str) -> Optional[list[float]]:
        """Encode a single text string into a float vector.

        Returns ``None`` if the model cannot be loaded (missing dependency,
        download failure, etc.).
        """
        if not text or not text.strip():
            return None

        if not self._load_model():
            return None

        try:
            # SentenceTransformer.encode returns numpy array
            embedding = self._model.encode(
                text,
                normalize_embeddings=self._normalize,
                show_progress_bar=False,
            )
            return embedding.tolist()
        except Exception as exc:
            logger.error("Encoding failed: %s", exc)
            return None

    def encode_batch(self, texts: list[str]) -> list[Optional[list[float]]]:
        """Encode multiple texts at once (uses batched inference).

        Returns a list with ``None`` entries for texts that failed to encode.
        Empty/whitespace-only texts get ``None``.
        """
        if not texts:
            return []

        # Filter out empty texts but track indices
        valid_indices: list[int] = []
        valid_texts: list[str] = []
        for i, t in enumerate(texts):
            if t and t.strip():
                valid_indices.append(i)
                valid_texts.append(t)

        results: list[Optional[list[float]]] = [None] * len(texts)

        if not valid_texts:
            return results

        if not self._load_model():
            return results

        try:
            embeddings = self._model.encode(
                valid_texts,
                normalize_embeddings=self._normalize,
                show_progress_bar=False,
                batch_size=32,
            )
            for idx, emb in zip(valid_indices, embeddings):
                results[idx] = emb.tolist()
        except Exception as exc:
            logger.error("Batch encoding failed: %s", exc)

        return results

    def __repr__(self) -> str:
        loaded = self._model is not None
        dim = self._dim or "?"
        return f"LocalEmbedder(model={self._model_name!r}, dim={dim}, loaded={loaded})"
