"""Tests for Guidelines CRUD, recommendation ingestion, and vector search."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from acp_writer.api import (
    app,
    _dynamic_models,
    _guidelines_store,
    _vector_store,
    init_stores,
)
from acp_writer.store.embedding import FakeEmbeddingProvider
from acp_writer.store.vector_store import InMemoryVectorStore

PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURES = PROJECT_ROOT / "shared" / "tests" / "fixtures"

client = TestClient(app)


def _load_sample_data() -> dict:
    return json.loads((FIXTURES / "sample-recommendations.json").read_text())


@pytest.fixture(autouse=True)
def reset_stores():
    """Reset stores between tests."""
    _dynamic_models.clear()
    init_stores(FakeEmbeddingProvider(dimensions=8))
    yield
    _dynamic_models.clear()
    init_stores(FakeEmbeddingProvider(dimensions=8))


class TestGuidelines:
    def test_list_empty(self):
        r = client.get("/api/v1/guidelines")
        assert r.status_code == 200
        assert r.json() == []

    def test_register(self):
        data = _load_sample_data()
        r = client.post("/api/v1/guidelines", json=data["metadata"])
        assert r.status_code == 201
        assert r.json()["cpg_id"] == "SYN-HTN-2026-001"
        assert r.json()["title"] == "Clinical Practice Guideline: Initial Management of Hypertension in Adults"

    def test_list_after_register(self):
        data = _load_sample_data()
        client.post("/api/v1/guidelines", json=data["metadata"])
        r = client.get("/api/v1/guidelines")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_get(self):
        data = _load_sample_data()
        client.post("/api/v1/guidelines", json=data["metadata"])
        r = client.get("/api/v1/guidelines/SYN-HTN-2026-001")
        assert r.status_code == 200
        assert r.json()["cpg_id"] == "SYN-HTN-2026-001"

    def test_get_not_found(self):
        r = client.get("/api/v1/guidelines/nonexistent")
        assert r.status_code == 404

    def test_delete(self):
        data = _load_sample_data()
        client.post("/api/v1/guidelines", json=data["metadata"])
        r = client.delete("/api/v1/guidelines/SYN-HTN-2026-001")
        assert r.status_code == 204
        r = client.get("/api/v1/guidelines")
        assert r.json() == []

    def test_delete_not_found(self):
        r = client.delete("/api/v1/guidelines/nonexistent")
        assert r.status_code == 404

    def test_invalid_metadata(self):
        r = client.post("/api/v1/guidelines", json={"not": "valid"})
        assert r.status_code == 400


class TestRecommendationIngestion:
    def test_ingest_single(self):
        data = _load_sample_data()
        rec = data["recommendation_bundle"]["recommendations"][0]
        r = client.post("/api/v1/knowledge/recommendations", json=rec)
        assert r.status_code == 201
        assert r.json()["status"] == "ingested"

    def test_ingest_batch(self):
        data = _load_sample_data()
        r = client.post(
            "/api/v1/knowledge/recommendations/batch",
            json=data["recommendation_bundle"],
        )
        assert r.status_code == 201
        body = r.json()
        assert body["source_cpg"] == "SYN-HTN-2026-001"
        assert body["count"] == 12

    def test_list_after_ingest(self):
        data = _load_sample_data()
        client.post(
            "/api/v1/knowledge/recommendations/batch",
            json=data["recommendation_bundle"],
        )
        r = client.get("/api/v1/knowledge/recommendations")
        assert r.status_code == 200
        assert len(r.json()) == 12

    def test_list_filter_by_cpg(self):
        data = _load_sample_data()
        client.post(
            "/api/v1/knowledge/recommendations/batch",
            json=data["recommendation_bundle"],
        )
        r = client.get("/api/v1/knowledge/recommendations?source_cpg=SYN-HTN-2026-001")
        assert len(r.json()) == 12
        r = client.get("/api/v1/knowledge/recommendations?source_cpg=nonexistent")
        assert len(r.json()) == 0

    def test_get_recommendation(self):
        data = _load_sample_data()
        rec = data["recommendation_bundle"]["recommendations"][0]
        client.post("/api/v1/knowledge/recommendations", json=rec)
        r = client.get(f"/api/v1/knowledge/recommendations/{rec['id']}")
        assert r.status_code == 200
        assert r.json()["title"] == rec["title"]

    def test_get_recommendation_not_found(self):
        r = client.get("/api/v1/knowledge/recommendations/nonexistent")
        assert r.status_code == 404

    def test_invalid_recommendation(self):
        r = client.post("/api/v1/knowledge/recommendations", json={"not": "valid"})
        assert r.status_code == 400


class TestSearch:
    def _ingest_all(self):
        data = _load_sample_data()
        client.post(
            "/api/v1/knowledge/recommendations/batch",
            json=data["recommendation_bundle"],
        )

    def test_search_returns_results(self):
        self._ingest_all()
        r = client.post(
            "/api/v1/knowledge/search",
            json={"query": "hypertension medication treatment", "top_k": 5},
        )
        assert r.status_code == 200
        results = r.json()["results"]
        assert len(results) > 0
        assert len(results) <= 5
        assert all("score" in res for res in results)

    def test_search_empty_store(self):
        r = client.post(
            "/api/v1/knowledge/search",
            json={"query": "hypertension"},
        )
        assert r.status_code == 200
        assert r.json()["results"] == []

    def test_search_filter_by_cpg(self):
        self._ingest_all()
        r = client.post(
            "/api/v1/knowledge/search",
            json={"query": "medication", "source_cpg": "nonexistent"},
        )
        assert r.json()["results"] == []

    def test_search_filter_by_type(self):
        self._ingest_all()
        r = client.post(
            "/api/v1/knowledge/search",
            json={"query": "therapy", "recommendation_type": "treatment"},
        )
        results = r.json()["results"]
        for res in results:
            assert res["recommendation"]["recommendation_type"] == "treatment"

    def test_search_filter_by_strength(self):
        self._ingest_all()
        r = client.post(
            "/api/v1/knowledge/search",
            json={"query": "therapy", "strength_in": ["strong-for"]},
        )
        results = r.json()["results"]
        for res in results:
            if res["recommendation"].get("certainty"):
                assert res["recommendation"]["certainty"]["strength"] == "strong-for"

    def test_search_results_have_excerpts(self):
        self._ingest_all()
        r = client.post(
            "/api/v1/knowledge/search",
            json={"query": "blood pressure"},
        )
        results = r.json()["results"]
        assert len(results) > 0
        assert all(res["excerpt"] is not None for res in results)

    def test_search_results_sorted_by_score(self):
        self._ingest_all()
        r = client.post(
            "/api/v1/knowledge/search",
            json={"query": "blood pressure", "top_k": 10},
        )
        results = r.json()["results"]
        scores = [res["score"] for res in results]
        assert scores == sorted(scores, reverse=True)


class TestCascadeDelete:
    def test_guideline_delete_cascades_recommendations(self):
        data = _load_sample_data()
        client.post("/api/v1/guidelines", json=data["metadata"])
        client.post(
            "/api/v1/knowledge/recommendations/batch",
            json=data["recommendation_bundle"],
        )

        r = client.get("/api/v1/knowledge/recommendations")
        assert len(r.json()) == 12

        r = client.delete("/api/v1/guidelines/SYN-HTN-2026-001")
        assert r.status_code == 204

        r = client.get("/api/v1/knowledge/recommendations")
        assert len(r.json()) == 0


class TestStatus:
    def test_status_shows_knowledge_counts(self):
        data = _load_sample_data()
        client.post("/api/v1/guidelines", json=data["metadata"])
        client.post(
            "/api/v1/knowledge/recommendations/batch",
            json=data["recommendation_bundle"],
        )

        r = client.get("/api/v1/status")
        assert r.status_code == 200
        kb = r.json()["knowledge_base"]
        assert kb["status"] == "available"
        assert kb["guidelines_registered"] == 1
        assert kb["recommendations_ingested"] == 12
