"""Tests for cpg_contracts types — serialization roundtrips and validation."""

import json
from pathlib import Path

from cpg_contracts import (
    CPGMetadata,
    DecisionModelSummary,
    Recommendation,
    RecommendationBundle,
    SourceLocation,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_source_location_full():
    loc = SourceLocation(
        page_start=12,
        page_end=13,
        bbox=[108.0, 273.0, 504.0, 176.8],
        source_text="All patients presenting with elevated blood pressure...",
    )
    assert loc.page_start == 12
    assert loc.page_end == 13
    assert len(loc.bbox) == 4
    data = loc.model_dump()
    assert SourceLocation(**data) == loc


def test_source_location_minimal():
    loc = SourceLocation(page_start=5)
    assert loc.page_end is None
    assert loc.bbox is None
    assert loc.source_text is None


def test_recommendation_with_source_location():
    rec = Recommendation(
        id="test-id",
        source_cpg="CPG-001",
        title="Test",
        content="Test content",
        recommendation_type="treatment",
        source_location=SourceLocation(page_start=10, page_end=11),
    )
    data = rec.model_dump()
    assert data["source_location"]["page_start"] == 10
    roundtrip = Recommendation(**data)
    assert roundtrip.source_location.page_start == 10


def test_recommendation_without_source_location():
    rec = Recommendation(
        id="test-id",
        source_cpg="CPG-001",
        title="Test",
        content="Test content",
        recommendation_type="treatment",
    )
    assert rec.source_location is None


def test_decision_model_summary_with_source_location():
    dm = DecisionModelSummary(
        id="dm-1",
        name="BP Treatment",
        inputs=[],
        outputs=[],
        source_cpg="CPG-001",
        source_location=SourceLocation(
            page_start=47,
            page_end=48,
            source_text="Table 3. Blood pressure treatment thresholds",
        ),
    )
    data = dm.model_dump()
    assert data["source_location"]["page_start"] == 47
    assert data["source_location"]["source_text"].startswith("Table 3")


def test_sample_fixture_roundtrip():
    raw = json.loads((FIXTURES / "sample-recommendations.json").read_text())
    metadata = CPGMetadata(**raw["metadata"])
    bundle = RecommendationBundle(**raw["recommendation_bundle"])
    assert metadata.cpg_id == bundle.source_cpg

    with_location = [r for r in bundle.recommendations if r.source_location]
    assert len(with_location) >= 2
    for rec in with_location:
        assert rec.source_location.page_start > 0
        assert rec.source_location.source_text is not None

    without_location = [r for r in bundle.recommendations if not r.source_location]
    assert len(without_location) > 0
