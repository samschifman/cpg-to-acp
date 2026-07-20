"""Tests for cpg-ingester state definitions."""

from cpg_ingester.state import CPGIngesterState, DMNPipelineState, RecPipelineState


def test_ingester_state_empty():
    state: CPGIngesterState = {}
    assert isinstance(state, dict)


def test_ingester_state_with_run_id():
    state: CPGIngesterState = {"run_id": "abc123", "pdf_path": "/tmp/test.pdf"}
    assert state["run_id"] == "abc123"


def test_dmn_pipeline_state():
    state: DMNPipelineState = {"item": {"id": "test"}, "review_count": 0}
    assert state["review_count"] == 0


def test_rec_pipeline_state():
    state: RecPipelineState = {"items": [{"id": "r1"}], "review_count": 0}
    assert len(state["items"]) == 1
