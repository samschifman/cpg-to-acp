"""Regression test for conflict surfacing in the split / SonataFlow path.

The cluster runs the pod-split services, not the monolith ``pipeline.py``. The
``ComposePlan`` SonataFlow state calls the llm-reasoning pod's ``/api/v1/compose``
(and ``/api/v1/compose-async``) endpoint. Conflict detection must run there —
otherwise conflicts never surface in a deployed run (see issue #169).

These tests exercise the compose endpoints with a mocked LLM and assert that the
returned planning brief carries analyst-detected conflicts.
"""

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from acp_writer.services import llm_reasoning


client = TestClient(llm_reasoning.app)


def _composed_brief() -> dict:
    """A converged brief with two same-diet activities — no conflicts annotated
    yet (the composer never flags them; the analyst does)."""
    return {
        "patient_reference": "Patient/1",
        "applicable_cpgs": ["SYN-HTN-2026-001", "SYN-DM2-2026-001"],
        "goals": [],
        "activities": [
            {"type": "lifestyle", "description": "Adopt a healthy diet",
             "source_cpg": "SYN-HTN-2026-001", "source_recommendation_id": "htn-rec-004"},
            {"type": "lifestyle", "description": "Follow a heart-healthy diet",
             "source_cpg": "SYN-DM2-2026-001", "source_recommendation_id": "dm2-rec-004"},
        ],
        "conflicts": [],
        "review_status": "approved",
    }


_OVERLAP_JSON = json.dumps({
    "conflicts": [{
        "category": "overlap",
        "severity": "info",
        "description": "Both guidelines recommend a healthy diet",
        "rationale": "Two lifestyle diet activities are substantially the same",
        "confidence": "high",
        "goal_indices": [],
        "activity_indices": [0, 1],
        "sources": [
            {"cpg_id": "SYN-HTN-2026-001", "recommendation_id": "htn-rec-004", "excerpt": "healthy diet"},
            {"cpg_id": "SYN-DM2-2026-001", "recommendation_id": "dm2-rec-004", "excerpt": "heart-healthy diet"},
        ],
    }]
})


def _mock_llm(content: str) -> MagicMock:
    mock = MagicMock()
    resp = MagicMock()
    resp.content = content
    mock.invoke.return_value = resp
    return mock


_COMPOSE_PAYLOAD = {
    "patient_reference": "Patient/1",
    "recommendations": [
        {"id": "htn-rec-004", "title": "Diet", "content": "Adopt a healthy diet", "source_cpg": "SYN-HTN-2026-001"},
        {"id": "dm2-rec-004", "title": "Diet", "content": "Follow a heart-healthy diet", "source_cpg": "SYN-DM2-2026-001"},
    ],
    "applicable_cpgs": ["SYN-HTN-2026-001", "SYN-DM2-2026-001"],
    "condition_codes": [{"display": "Hypertension"}, {"display": "Type 2 diabetes"}],
}


def test_compose_runs_conflict_analyst():
    """The sync /compose endpoint must run the conflict analyst so the returned
    brief carries conflicts (regression: it previously stopped after the
    brief-review loop and never invoked the analyst)."""
    with patch.object(llm_reasoning, "_phi_store", None), \
         patch.object(llm_reasoning, "plan_composer",
                      return_value={"planning_brief": _composed_brief()}), \
         patch.object(llm_reasoning, "brief_reviewer",
                      return_value={"brief_review_feedback": "", "brief_review_count": 1}), \
         patch("acp_writer.nodes.conflict_analyst.get_llm",
               return_value=_mock_llm(_OVERLAP_JSON)):
        resp = client.post("/api/v1/compose", json=_COMPOSE_PAYLOAD)

    assert resp.status_code == 200
    brief = resp.json()["planning_brief"]
    conflicts = brief["conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["category"] == "overlap"
    assert conflicts[0]["activity_indices"] == [0, 1]


def test_compose_async_runs_conflict_analyst():
    """The async /compose-async background task must also run the analyst; the
    conflicts ride the brief in the callback payload."""
    captured = {}

    def _capture(callback_url, process_instance_id, event, result):
        captured["result"] = result

    with patch.object(llm_reasoning, "_phi_store", None), \
         patch.object(llm_reasoning, "plan_composer",
                      return_value={"planning_brief": _composed_brief()}), \
         patch.object(llm_reasoning, "brief_reviewer",
                      return_value={"brief_review_feedback": "", "brief_review_count": 1}), \
         patch("acp_writer.nodes.conflict_analyst.get_llm",
               return_value=_mock_llm(_OVERLAP_JSON)), \
         patch.object(llm_reasoning, "post_callback", _capture):
        payload = dict(_COMPOSE_PAYLOAD, callback_url="http://cb", process_instance_id="pi-1")
        resp = client.post("/api/v1/compose-async", json=payload)

    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    brief = captured["result"]["planning_brief"]
    conflicts = brief["conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["category"] == "overlap"
