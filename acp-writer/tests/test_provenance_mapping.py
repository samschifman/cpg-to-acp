"""Unit tests for the review-gate provenance mappers (#128).

These map planning-brief snake_case goals/activities → BFF camelCase, mirroring
``plan_conflict_from_entry``.
"""

from acp_writer.services.artifact_resolver import (
    _format_brief_goal_target,
)


class TestFormatBriefGoalTarget:
    def test_measure_with_upper_bound(self):
        s = _format_brief_goal_target(
            {"display": "HbA1c", "code": "4548-4"}, {"high": 7, "unit": "%"}
        )
        assert s == "HbA1c < 7 %"

    def test_measure_with_lower_bound(self):
        s = _format_brief_goal_target({"display": "Steps"}, {"low": 8000, "unit": "count"})
        assert s == "Steps > 8000 count"

    def test_measure_with_range(self):
        s = _format_brief_goal_target(
            {"display": "SBP"}, {"low": 110, "high": 130, "unit": "mmHg"}
        )
        assert s == "SBP: 110–130 mmHg"

    def test_falls_back_to_code_when_no_display(self):
        s = _format_brief_goal_target({"code": "4548-4"}, {"high": 7, "unit": "%"})
        assert s == "4548-4 < 7 %"

    def test_measure_only(self):
        assert _format_brief_goal_target({"display": "HbA1c"}, None) == "HbA1c"

    def test_empty(self):
        assert _format_brief_goal_target(None, None) == ""
        assert _format_brief_goal_target({}, {}) == ""
