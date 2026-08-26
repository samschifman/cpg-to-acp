"""Tests for the DMN generation loop mechanics: separate retry budgets,
repair-mode feedback, escalation propagation, and the no-silent-drop guarantee.
"""

from unittest.mock import MagicMock, patch

from cpg_ingester import generation
from cpg_ingester.generation import (
    MAX_DMN_SEMANTIC_RETRIES,
    MAX_DMN_SYNTAX_RETRIES,
    _dmn_escalate,
    _route_after_dmn_semantic,
    _route_after_dmn_syntax,
    generate_all,
)
from cpg_ingester.nodes.dmn_creator import _build_feedback
from cpg_ingester.reference.dmn_error_patterns import (
    format_error_pattern_hints,
    match_error_patterns,
)


class TestSeparateBudgets:
    def test_syntax_retries_until_budget_then_escalates(self):
        assert _route_after_dmn_syntax(
            {"syntax_errors": ["e"], "syntax_retry_count": 0}) == "dmn_creator"
        assert _route_after_dmn_syntax(
            {"syntax_errors": ["e"], "syntax_retry_count": MAX_DMN_SYNTAX_RETRIES}) == "dmn_escalate"

    def test_clean_syntax_advances_to_review(self):
        assert _route_after_dmn_syntax({"syntax_errors": []}) == "dmn_semantic_reviewer"

    def test_semantic_budget_is_independent_of_syntax(self):
        # A high syntax count must not push the semantic loop into escalation.
        state = {"semantic_discrepancies": ["d"], "semantic_retry_count": 0,
                 "syntax_retry_count": 99}
        assert _route_after_dmn_semantic(state) == "dmn_creator"
        state["semantic_retry_count"] = MAX_DMN_SEMANTIC_RETRIES
        assert _route_after_dmn_semantic(state) == "dmn_escalate"

    def test_force_escalate_bypasses_budget(self):
        assert _route_after_dmn_semantic(
            {"force_escalate": True, "semantic_discrepancies": [], "semantic_retry_count": 0}
        ) == "dmn_escalate"

    def test_clean_semantic_accepts(self):
        assert _route_after_dmn_semantic({"semantic_discrepancies": []}) == "dmn_accept"


class TestEscalateNode:
    def test_records_syntax_budget_reason(self):
        out = _dmn_escalate({"item": {"name": "X"}, "syntax_errors": ["bad"]})
        assert out["escalated"] is True
        assert out["escalation_reason"] == "syntax-budget-exhausted"
        assert out["escalation_errors"] == ["bad"]

    def test_reviewer_reason_takes_precedence(self):
        out = _dmn_escalate({"item": {"name": "X"}, "escalation_reason": "no-source-text",
                             "semantic_discrepancies": ["no source"]})
        assert out["escalation_reason"] == "no-source-text"


class TestRepairFeedback:
    def test_renders_both_sections_and_previous_xml(self):
        fb = _build_feedback(["missing hitPolicy"], ["threshold wrong"], "<definitions/>")
        assert "Syntax errors to fix" in fb
        assert "Semantic discrepancies to fix" in fb
        assert "<definitions/>" in fb
        assert "missing hitPolicy" in fb
        assert "threshold wrong" in fb

    def test_empty_when_no_errors(self):
        assert _build_feedback([], [], "<definitions/>") == ""

    def test_appends_known_error_pattern(self):
        fb = _build_feedback(["DecisionTable 'x': missing hitPolicy attribute"], [], "")
        assert "Known error patterns" in fb


class TestErrorPatternKB:
    def test_matches_missing_hit_policy(self):
        hits = match_error_patterns(["DecisionTable 'x': missing hitPolicy attribute"])
        assert hits
        assert any("hitPolicy" in h.fix for h in hits)

    def test_regex_pattern_matches_entry_count(self):
        hits = match_error_patterns(["Rule 'r1': has 2 inputEntries, expected 3"])
        assert hits

    def test_no_match_returns_empty(self):
        assert match_error_patterns(["something totally unrecognized xyzzy"]) == []
        assert format_error_pattern_hints(["xyzzy"]) == ""


class TestGenerateAllNoSilentDrop:
    """A decision must never vanish from the output — crashes and empty results
    both become flagged entries."""

    _MANIFEST = [{"type": "decision", "name": "D1", "section": "S1"}]

    def _run_with_graph(self, fake_graph):
        state = {"item_manifest": self._MANIFEST, "markdown": "", "section_map": []}
        with patch.object(generation, "_build_dmn_subgraph") as mock_builder, \
             patch.object(generation, "_build_rec_subgraph") as mock_rec:
            mock_builder.return_value.compile.return_value = fake_graph
            mock_rec.return_value.compile.return_value = MagicMock(invoke=MagicMock(return_value={}))
            return generate_all(state)

    def test_subgraph_exception_becomes_flagged_entry(self):
        graph = MagicMock()
        graph.invoke = MagicMock(side_effect=RuntimeError("boom"))
        result = self._run_with_graph(graph)
        assert len(result["dmn_results"]) == 1
        entry = result["dmn_results"][0]
        assert entry["escalated"] is True
        assert entry["escalation_reason"] == "generation-exception"

    def test_empty_result_becomes_flagged_entry(self):
        graph = MagicMock()
        graph.invoke = MagicMock(return_value={"dmn_xml": ""})
        result = self._run_with_graph(graph)
        assert len(result["dmn_results"]) == 1
        entry = result["dmn_results"][0]
        assert entry["escalated"] is True
        assert entry["escalation_reason"] == "empty-result"

    def test_escalated_result_carries_reason_and_errors(self):
        graph = MagicMock()
        graph.invoke = MagicMock(return_value={
            "dmn_xml": "<definitions/>",
            "escalated": True,
            "escalation_reason": "syntax-budget-exhausted",
            "escalation_errors": ["missing hitPolicy"],
        })
        result = self._run_with_graph(graph)
        entry = result["dmn_results"][0]
        assert entry["escalated"] is True
        assert entry["escalation_reason"] == "syntax-budget-exhausted"
        assert entry["escalation_errors"] == ["missing hitPolicy"]
