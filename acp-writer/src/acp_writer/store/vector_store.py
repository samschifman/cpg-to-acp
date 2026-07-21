"""Vector Store — pluggable recommendation storage and retrieval.

Default implementation uses in-memory cosine similarity for dev.
PostgreSQL + pgvector implementation for production (Phase 3.3).
"""

import logging
import math
from abc import ABC, abstractmethod

from cpg_contracts import (
    Recommendation,
    RecommendationSearchRequest,
    RecommendationSearchResponse,
    RecommendationSearchResult,
    RecommendationSummary,
)

from acp_writer.store.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)


class VectorStore(ABC):
    """Interface for recommendation vector storage and retrieval."""

    @abstractmethod
    def add(self, recommendation: Recommendation) -> None:
        """Embed and store a single recommendation."""

    @abstractmethod
    def add_batch(self, recommendations: list[Recommendation]) -> None:
        """Embed and store a batch of recommendations."""

    @abstractmethod
    def get(self, rec_id: str) -> Recommendation | None:
        """Retrieve a recommendation by ID."""

    @abstractmethod
    def list_all(self, source_cpg: str | None = None) -> list[Recommendation]:
        """List recommendations, optionally filtered by source CPG."""

    @abstractmethod
    def search(self, request: RecommendationSearchRequest) -> RecommendationSearchResponse:
        """Search recommendations by vector similarity + metadata filters."""

    @abstractmethod
    def delete_by_cpg(self, cpg_id: str) -> int:
        """Delete all recommendations for a CPG. Returns count deleted."""

    @abstractmethod
    def count(self) -> int:
        """Return total number of stored recommendations."""


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryVectorStore(VectorStore):
    """In-memory vector store using cosine similarity.

    Suitable for dev/testing with <1,000 recommendations.
    Sequential scan gives exact results at this scale.
    """

    def __init__(self, embedding_provider: EmbeddingProvider):
        self._provider = embedding_provider
        self._recs: dict[str, Recommendation] = {}
        self._embeddings: dict[str, list[float]] = {}

    def _embed_recommendation(self, rec: Recommendation) -> list[float]:
        text = f"{rec.title}\n{rec.content}"
        return self._provider.embed([text])[0]

    def add(self, recommendation: Recommendation) -> None:
        embedding = self._embed_recommendation(recommendation)
        self._recs[recommendation.id] = recommendation
        self._embeddings[recommendation.id] = embedding
        logger.debug("Stored recommendation: %s", recommendation.id)

    def add_batch(self, recommendations: list[Recommendation]) -> None:
        if not recommendations:
            return
        texts = [f"{r.title}\n{r.content}" for r in recommendations]
        embeddings = self._provider.embed(texts)
        for rec, emb in zip(recommendations, embeddings):
            self._recs[rec.id] = rec
            self._embeddings[rec.id] = emb
        logger.info("Stored %d recommendations", len(recommendations))

    def get(self, rec_id: str) -> Recommendation | None:
        return self._recs.get(rec_id)

    def list_all(self, source_cpg: str | None = None) -> list[Recommendation]:
        if source_cpg is None:
            return list(self._recs.values())
        return [r for r in self._recs.values() if r.source_cpg == source_cpg]

    def search(self, request: RecommendationSearchRequest) -> RecommendationSearchResponse:
        query_embedding = self._provider.embed([request.query])[0]

        scored: list[tuple[float, Recommendation]] = []
        for rec_id, emb in self._embeddings.items():
            rec = self._recs[rec_id]

            if request.source_cpg and rec.source_cpg != request.source_cpg:
                continue
            if request.recommendation_type and rec.recommendation_type != request.recommendation_type:
                continue
            if request.strength_in and rec.certainty:
                if rec.certainty.strength not in request.strength_in:
                    continue

            score = _cosine_similarity(query_embedding, emb)
            scored.append((score, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: request.top_k]

        results = [
            RecommendationSearchResult(
                recommendation=RecommendationSummary(
                    id=rec.id,
                    title=rec.title,
                    source_cpg=rec.source_cpg,
                    recommendation_type=rec.recommendation_type,
                    certainty=rec.certainty,
                ),
                score=score,
                excerpt=rec.content[:200],
            )
            for score, rec in top
        ]
        return RecommendationSearchResponse(results=results)

    def delete_by_cpg(self, cpg_id: str) -> int:
        to_delete = [rid for rid, r in self._recs.items() if r.source_cpg == cpg_id]
        for rid in to_delete:
            del self._recs[rid]
            del self._embeddings[rid]
        if to_delete:
            logger.info("Deleted %d recommendations for CPG %s", len(to_delete), cpg_id)
        return len(to_delete)

    def count(self) -> int:
        return len(self._recs)
