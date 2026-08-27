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

from acp_writer.services import fhir_generation, llm_reasoning


client = TestClient(llm_reasoning.app)


def _ai_input_prompts(bundle: dict) -> list[dict]:
    return [
        e["resource"]
        for e in bundle.get("entry", [])
        if e["resource"]["resourceType"] == "DocumentReference"
        and any(
            "AI-InputPrompt" in p
            for p in e["resource"].get("meta", {}).get("profile", [])
        )
    ]


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


def test_prompts_ferry_compose_to_generate_bundle():
    """F2: rendered prompts captured in the split compose service must reach the
    fhir-generation service so the DEPLOYED bundle carries AI-InputPrompt
    DocRefs, exactly as the monolith does. Before F2 the compose endpoint
    returned only the brief and dropped the prompts, so the split-path bundle
    silently lost prompt traceability (issue #169)."""
    composed = {
        "planning_brief": _composed_brief(),
        "plan_composer_prompt": "COMPOSE PROMPT — patient X",
    }
    with patch.object(llm_reasoning, "_phi_store", None), \
         patch.object(llm_reasoning, "plan_composer", return_value=composed), \
         patch.object(llm_reasoning, "brief_reviewer",
                      return_value={"brief_review_feedback": "", "brief_review_count": 1}), \
         patch("acp_writer.nodes.conflict_analyst.get_llm",
               return_value=_mock_llm(_OVERLAP_JSON)):
        compose_resp = client.post("/api/v1/compose", json=_COMPOSE_PAYLOAD)

    assert compose_resp.status_code == 200
    compose_out = compose_resp.json()
    # Prompts must be ferried out of compose (inline when no PHI store).
    assert "prompts" in compose_out
    assert compose_out["prompts"].get("plan_composer_prompt") == "COMPOSE PROMPT — patient X"
    assert compose_out["prompts"].get("conflict_prompt")

    gen_client = TestClient(fhir_generation.app)
    with patch.object(fhir_generation, "_phi_store", None):
        gen_resp = gen_client.post("/api/v1/generate-bundle", json={
            "planning_brief": compose_out["planning_brief"],
            "prompts": compose_out["prompts"],
        })

    assert gen_resp.status_code == 200
    bundle = gen_resp.json()["fhir_bundle"]
    input_prompts = _ai_input_prompts(bundle)
    assert input_prompts, "deployed bundle lost AI-InputPrompt DocRefs (F2)"


def test_seed_feedback_comment_and_conflicts():
    """F16a: _seed_feedback emits the clinician comment followed by the prior
    conflicts block so 'resolve the identified conflicts' has a referent."""
    fb = llm_reasoning._seed_feedback(
        "resolve all identified conflicts as you suggested",
        [{"id": "conf-1", "category": "overlap", "description": "two diets",
          "suggested_resolution": "combine them"}],
    )
    assert "resolve all identified conflicts as you suggested" in fb
    assert "## Previously identified conflicts" in fb
    assert "two diets" in fb
    assert "Suggested: combine them" in fb


def test_seed_feedback_comment_only_when_no_prior_conflicts():
    """Control: no prior conflicts → comment only, no conflicts block."""
    fb = llm_reasoning._seed_feedback("please revise the plan", [])
    assert "please revise the plan" in fb
    assert "## Previously identified conflicts" not in fb


def test_seed_feedback_empty_on_first_pass():
    assert llm_reasoning._seed_feedback("", []) == ""


def test_prior_conflicts_seed_the_composer_feedback():
    """F16a end-to-end through /compose: a request-changes call carrying the
    prior brief ref threads the previously-detected conflicts into the composer's
    seeded feedback. Before F16a only the free-text comment reached the composer,
    leaving 'resolve the identified conflicts' with nothing to act on."""
    captured = {}

    def _capture_compose(state):
        captured["feedback"] = state.get("brief_review_feedback", "")
        return {"planning_brief": _composed_brief()}

    prior_brief = {
        "conflicts": [{
            "id": "conf-xyz", "category": "overlap", "severity": "info",
            "description": "Both guidelines recommend a healthy diet",
            "suggested_resolution": "Combine the two diet activities into one",
            "sources": [{"cpg_id": "SYN-HTN-2026-001", "recommendation_id": "htn-rec-004"}],
        }],
    }
    with patch.object(llm_reasoning, "_phi_store", None), \
         patch.object(llm_reasoning, "plan_composer", side_effect=_capture_compose), \
         patch.object(llm_reasoning, "brief_reviewer",
                      return_value={"brief_review_feedback": "", "brief_review_count": 1}), \
         patch("acp_writer.nodes.conflict_analyst.get_llm",
               return_value=_mock_llm(_OVERLAP_JSON)):
        # prior_brief_ref (truthy) passes the guard; with _phi_store None the
        # resolver falls back to the inline prior_brief payload.
        payload = dict(
            _COMPOSE_PAYLOAD,
            careplan_feedback="resolve all identified conflicts as you suggested",
            prior_brief_ref="phi:prior-brief",
            prior_brief=prior_brief,
        )
        resp = client.post("/api/v1/compose", json=payload)

    assert resp.status_code == 200
    fb = captured["feedback"]
    assert "resolve all identified conflicts as you suggested" in fb
    assert "## Previously identified conflicts" in fb
    assert "Both guidelines recommend a healthy diet" in fb
    assert "Suggested: Combine the two diet activities into one" in fb


def test_first_pass_has_no_prior_conflict_block():
    """Control for F16a: first pass (no prior_brief_ref) → empty seeded feedback."""
    captured = {}

    def _capture_compose(state):
        captured["feedback"] = state.get("brief_review_feedback", "")
        return {"planning_brief": _composed_brief()}

    with patch.object(llm_reasoning, "_phi_store", None), \
         patch.object(llm_reasoning, "plan_composer", side_effect=_capture_compose), \
         patch.object(llm_reasoning, "brief_reviewer",
                      return_value={"brief_review_feedback": "", "brief_review_count": 1}), \
         patch("acp_writer.nodes.conflict_analyst.get_llm",
               return_value=_mock_llm(_OVERLAP_JSON)):
        resp = client.post("/api/v1/compose", json=_COMPOSE_PAYLOAD)

    assert resp.status_code == 200
    assert captured["feedback"] == ""


def test_generate_bundle_without_prompts_has_no_input_prompt_docrefs():
    """Control for F2: no ferried prompts → no AI-InputPrompt DocRefs. Proves the
    ferry is what puts them in the deployed bundle, not the brief alone."""
    gen_client = TestClient(fhir_generation.app)
    with patch.object(fhir_generation, "_phi_store", None):
        gen_resp = gen_client.post("/api/v1/generate-bundle", json={
            "planning_brief": _composed_brief(),
        })

    assert gen_resp.status_code == 200
    assert _ai_input_prompts(gen_resp.json()["fhir_bundle"]) == []
