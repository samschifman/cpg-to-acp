"""Contract types for recommendation search."""

from pydantic import BaseModel

from cpg_contracts.recommendations import (
    RecommendationStrength,
    RecommendationSummary,
    RecommendationType,
)


class RecommendationSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    source_cpg: str | None = None
    recommendation_type: RecommendationType | None = None
    strength_in: list[RecommendationStrength] | None = None


class RecommendationSearchResult(BaseModel):
    recommendation: RecommendationSummary
    score: float
    excerpt: str | None = None


class RecommendationSearchResponse(BaseModel):
    results: list[RecommendationSearchResult]
