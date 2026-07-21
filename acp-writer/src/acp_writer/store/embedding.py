"""Pluggable embedding provider interface.

Organizations can substitute any model due to domain preferences,
legal restrictions, or compliance requirements. Default uses
NeuML/pubmedbert-base-embeddings (local, clinical-domain).
"""

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Interface for producing vector embeddings from text."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts into vectors."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Dimensionality of the embedding vectors."""


class SentenceTransformerProvider(EmbeddingProvider):
    """Embedding provider using sentence-transformers models.

    Default model: NeuML/pubmedbert-base-embeddings (768 dims, clinical-domain).
    Override via EMBEDDING_MODEL env var or constructor argument.
    """

    def __init__(self, model_name: str | None = None):
        self._model_name = (
            model_name
            or os.environ.get("EMBEDDING_MODEL", "NeuML/pubmedbert-base-embeddings")
        )
        self._model = None
        self._dims: int | None = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
            self._dims = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        embeddings = self._model.encode(texts, show_progress_bar=False)
        return [e.tolist() for e in embeddings]

    @property
    def dimensions(self) -> int:
        self._load_model()
        return self._dims


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic fake provider for testing. Produces fixed-dimension vectors."""

    def __init__(self, dimensions: int = 8):
        self._dims = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            h = hash(text) & 0xFFFFFFFF
            vec = []
            for i in range(self._dims):
                val = ((h * (i + 1) * 2654435761) & 0xFFFFFFFF) / 0xFFFFFFFF
                vec.append(val * 2 - 1)
            norm = sum(v * v for v in vec) ** 0.5
            if norm > 0:
                vec = [v / norm for v in vec]
            result.append(vec)
        return result

    @property
    def dimensions(self) -> int:
        return self._dims
