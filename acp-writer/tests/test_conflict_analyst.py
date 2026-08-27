"""Tests for the Conflict Analyst node."""

import json
from unittest.mock import MagicMock, patch

from acp_writer.nodes.conflict_analyst import conflict_analyst
from acp_writer.planning_brief import ConflictEntry


def _brief() -> dict:
    return {
        "patient_reference": "Patient/1",
        "applicable_cpgs": ["SYN-HTN-2026-001", "SYN-DM2-2026-001"],
        "goals": [
            {
                "description": "Lower BP to < 140/90",
                "target_measure_code": {"system": "http://loinc.org", "code": "8480-6", "display": "Systolic BP"},
                "target_value": {"high": 140, "unit": "mmHg"},
                "source_cpg": "SYN-HTN-2026-001",
                "source_recommendation_id": "htn-rec-002",
            },
            {
                "description": "Lower BP to < 130/80",
                "target_measure_code": {"system": "http://loinc.org", "code": "8480-6", "display": "Systolic BP"},
                "target_value": {"high": 130, "unit": "mmHg"},
                "source_cpg": "SYN-DM2-2026-001",
                "source_recommendation_id": "dm2-rec-002",
            },
        ],
        "activities": [
            {"type": "lifestyle", "description": "Adopt a healthy diet", "source_cpg": "SYN-HTN-2026-001", "source_recommendation_id": "htn-rec-004"},
            {"type": "lifestyle", "description": "Follow a heart-healthy diet", "source_cpg": "SYN-DM2-2026-001", "source_recommendation_id": "dm2-rec-004"},
            {"type": "medication", "description": "Lisinopril 10mg daily", "code": {"system": "rxnorm", "code": "29046", "display": "Lisinopril"}, "source_cpg": "SYN-HTN-2026-001", "source_recommendation_id": "htn-rec-001"},
        ],
        "conflicts": [],
        "review_status": "approved",
    }


def _state(brief: dict | None = None) -> dict:
    return {
        "planning_brief": brief if brief is not None else _brief(),
        "recommendations": [
            {"id": "htn-rec-004", "title": "Diet", "content": "Adopt a healthy diet", "source_cpg": "SYN-HTN-2026-001"},
            {"id": "dm2-rec-004", "title": "Diet", "content": "Follow a heart-healthy diet", "source_cpg": "SYN-DM2-2026-001"},
        ],
        "condition_codes": [{"display": "Hypertension"}, {"display": "Type 2 diabetes"}],
        "medication_codes": [{"display": "Lisinopril"}],
        "llm_model": "default",
    }


def _mock_llm(*contents):
    """Return a mock get_llm whose invoke yields the given contents in order."""
    mock = MagicMock()
    responses = []
    for c in contents:
        r = MagicMock()
        r.content = c
        responses.append(r)
    mock.invoke.side_effect = responses
    return mock


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


class TestConflictAnalyst:
    @patch("acp_writer.nodes.conflict_analyst.get_llm")
    def test_happy_path(self, mock_get_llm):
        mock_get_llm.return_value = _mock_llm(_OVERLAP_JSON)
        result = conflict_analyst(_state())

        conflicts = result["planning_brief"]["conflicts"]
        assert len(conflicts) == 1
        c = ConflictEntry.model_validate(conflicts[0])
        assert c.category.value == "overlap"
        assert c.activity_indices == [0, 1]
        assert c.detected_by == "llm"
        assert c.id.startswith("conf-")
        assert "conflict_prompt" in result

    @patch("acp_writer.nodes.conflict_analyst.get_llm")
    def test_index_clamping(self, mock_get_llm):
        raw = json.loads(_OVERLAP_JSON)
        raw["conflicts"][0]["activity_indices"] = [0, 99]  # 99 is out of range
        mock_get_llm.return_value = _mock_llm(json.dumps(raw))
        result = conflict_analyst(_state())
        assert result["planning_brief"]["conflicts"][0]["activity_indices"] == [0]

    @patch("acp_writer.nodes.conflict_analyst.get_llm")
    def test_drops_entry_with_all_invalid_indices(self, mock_get_llm):
        raw = json.loads(_OVERLAP_JSON)
        raw["conflicts"][0]["activity_indices"] = [99]
        raw["conflicts"][0]["goal_indices"] = [88]
        mock_get_llm.return_value = _mock_llm(json.dumps(raw))
        result = conflict_analyst(_state())
        assert result["planning_brief"]["conflicts"] == []

    @patch("acp_writer.nodes.conflict_analyst.get_llm")
    def test_retry_then_succeed(self, mock_get_llm):
        mock = _mock_llm("not json at all", _OVERLAP_JSON)
        mock_get_llm.return_value = mock
        result = conflict_analyst(_state())
        assert len(result["planning_brief"]["conflicts"]) == 1
        assert mock.invoke.call_count == 2

    @patch("acp_writer.nodes.conflict_analyst.get_llm")
    def test_degradation_keeps_existing_conflicts(self, mock_get_llm):
        mock_get_llm.return_value = _mock_llm("garbage", "still garbage")
        brief = _brief()
        brief["conflicts"] = [{
            "id": "conf-prior", "category": "overlap", "severity": "info",
            "description": "pre-existing", "detected_by": "composer",
            "activity_indices": [0], "sources": [],
        }]
        result = conflict_analyst(_state(brief))
        # Existing conflicts are preserved, run does not raise.
        assert result["planning_brief"]["conflicts"][0]["id"] == "conf-prior"

    @patch("acp_writer.nodes.conflict_analyst.get_llm")
    def test_transport_failure_degrades(self, mock_get_llm):
        mock = MagicMock()
        mock.invoke.side_effect = RuntimeError("connection reset")
        mock_get_llm.return_value = mock
        result = conflict_analyst(_state())  # must not raise
        assert result["planning_brief"]["conflicts"] == []

    @patch("acp_writer.nodes.conflict_analyst.get_llm")
    def test_composer_conflict_superseded(self, mock_get_llm):
        mock_get_llm.return_value = _mock_llm(_OVERLAP_JSON)
        brief = _brief()
        brief["conflicts"] = [{
            "id": "conf-old", "category": "overlap", "severity": "info",
            "description": "composer's overlap on the same diet activities",
            "detected_by": "composer", "activity_indices": [0], "sources": [],
        }]
        result = conflict_analyst(_state(brief))
        conflicts = result["planning_brief"]["conflicts"]
        assert len(conflicts) == 1  # composer's version dropped in favor of analyst's
        assert conflicts[0]["detected_by"] == "llm"

    @patch("acp_writer.nodes.conflict_analyst.get_llm")
    def test_composer_conflict_retained_when_distinct(self, mock_get_llm):
        mock_get_llm.return_value = _mock_llm(_OVERLAP_JSON)
        brief = _brief()
        brief["conflicts"] = [{
            "id": "conf-distinct", "category": "contradiction", "severity": "warning",
            "description": "composer flagged the medication",
            "detected_by": "composer", "activity_indices": [2], "sources": [],
        }]
        result = conflict_analyst(_state(brief))
        ids = {c["id"] for c in result["planning_brief"]["conflicts"]}
        assert "conf-distinct" in ids  # untouched by analyst → kept
        assert len(ids) == 2

    @patch("acp_writer.nodes.conflict_analyst.get_llm")
    def test_carry_forward_status(self, mock_get_llm):
        mock_get_llm.return_value = _mock_llm(_OVERLAP_JSON)
        # Precompute the id the analyst will assign, then seed a prior
        # acknowledged conflict with that id so status carries forward.
        first = conflict_analyst(_state())
        cid = first["planning_brief"]["conflicts"][0]["id"]

        brief = _brief()
        brief["conflicts"] = [{
            "id": cid, "category": "overlap", "severity": "info",
            "description": "acknowledged earlier", "detected_by": "llm",
            "status": "acknowledged", "resolution": "clinician noted",
            "activity_indices": [0, 1], "sources": [],
        }]
        mock_get_llm.return_value = _mock_llm(_OVERLAP_JSON)
        result = conflict_analyst(_state(brief))
        c = result["planning_brief"]["conflicts"][0]
        assert c["status"] == "acknowledged"
        assert c["resolution"] == "clinician noted"

    @patch("acp_writer.nodes.conflict_analyst.get_llm")
    def test_empty_brief_passthrough(self, mock_get_llm):
        brief = _brief()
        brief["goals"] = []
        brief["activities"] = []
        result = conflict_analyst(_state(brief))
        assert result["planning_brief"]["conflicts"] == []
        mock_get_llm.assert_not_called()
