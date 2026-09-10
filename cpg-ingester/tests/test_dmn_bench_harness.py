"""Tests for harness scoring/classification logic (no network, no LLM)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

# The DMN benchmark is a non-package folder under tests/benchmarks/dmn (mirrors
# tests/benchmarks/parsing); put it on sys.path so its modules import by bare name.
_BENCH = Path(__file__).parent / "benchmarks" / "dmn"
sys.path.insert(0, str(_BENCH))

import compile_check as cc
from creator_eval import CreatorResult, _aggregate, _source_text
from reviewer_eval import ReviewerCase, _score
from cpg_ingester.validators.dmn_schema import validate_dmn_schema
from cpg_ingester.validators.dmn_syntax import validate_dmn

INGESTER_ROOT = Path(__file__).parent.parent


class TestCompileClassification:
    def _resp(self, status, text=""):
        r = MagicMock()
        r.status_code = status
        r.text = text
        return r

    def test_200_and_422_are_compile_ok(self):
        with patch("compile_check.requests.post", return_value=self._resp(200)):
            assert cc.compile_check("<x/>").status == "COMPILE_OK"
        with patch("compile_check.requests.post", return_value=self._resp(422, "eval err")):
            assert cc.compile_check("<x/>").status == "COMPILE_OK"

    def test_500_with_marker_is_compile_fail(self):
        body = "DMN evaluation failed: Failed to build DMN runtime: ..."
        with patch("compile_check.requests.post", return_value=self._resp(500, body)):
            assert cc.compile_check("<x/>").status == "COMPILE_FAIL"

    def test_500_without_marker_is_infra_not_compile_fail(self):
        with patch("compile_check.requests.post", return_value=self._resp(500, "OOM")):
            assert cc.compile_check("<x/>").status == "INFRA"

    def test_unreachable_is_skipped(self):
        with patch("compile_check.requests.post", side_effect=cc.requests.ConnectionError()):
            assert cc.compile_check("<x/>").status == "SKIPPED"


class TestCreatorAggregate:
    def test_l0_pass_but_compile_fail_counted(self):
        results = [
            CreatorResult(decision="A", first_attempt_l0_pass=True, attempts_to_valid=1,
                          final_l0_valid=True, compile_status="COMPILE_FAIL"),
            CreatorResult(decision="B", first_attempt_l0_pass=False, attempts_to_valid=2,
                          final_l0_valid=True, compile_status="COMPILE_OK"),
        ]
        agg = _aggregate(results)
        assert agg["l0_pass_but_compile_fail"] == 1
        assert agg["first_attempt_validity_rate"] == 0.5
        assert agg["compile_pass_rate"] == 0.5
        assert agg["mean_attempts_to_valid"] == 1.5


class TestReviewerScore:
    def test_recall_precision_false_escalation(self):
        cases = [
            ReviewerCase("A", "clean", False, flagged=False),
            ReviewerCase("A", "threshold_shift", False, flagged=True),
            ReviewerCase("A", "drop_rule", False, flagged=False),   # missed
            ReviewerCase("A", "wrong_hit_policy", True, flagged=True),  # holdout, caught
        ]
        m = _score(cases)
        assert m["seeded_defects"] == 3
        assert m["caught_defects"] == 2
        assert m["overall_recall"] == round(2 / 3, 4)
        assert m["false_escalation_rate"] == 0.0
        assert m["per_defect_class"]["drop_rule"]["recall"] == 0.0
        assert m["holdout_set"]["seeded"] == 1
        assert m["tuning_set"]["seeded"] == 2

    def test_false_escalation_counts_clean_flags(self):
        cases = [
            ReviewerCase("A", "clean", False, flagged=True),   # false escalation
            ReviewerCase("A", "threshold_shift", False, flagged=True),
        ]
        m = _score(cases)
        assert m["false_escalation_rate"] == 1.0
        # precision = true flags / all flags = 1/2
        assert m["overall_precision"] == 0.5


class TestCorpusManifest:
    def test_manifest_loads_and_paths_exist(self):
        manifest = yaml.safe_load((_BENCH / "corpus.yaml").read_text())
        for corpus in manifest["corpora"].values():
            assert (INGESTER_ROOT / corpus["source_cpg"]).exists()
            assert corpus["decisions"]
            for dec in corpus["decisions"]:
                assert (INGESTER_ROOT / dec["golden"]).exists()
                assert dec["representative_inputs"]

    def test_source_line_ranges_narrow_broad_sections(self):
        markdown = "one\ntwo\nthree\nfour"
        assert _source_text(markdown, {"markdown_lines": "2-3"}) == "two\nthree"

    def test_all_manifest_goldens_pass_local_gates(self):
        manifest = yaml.safe_load((_BENCH / "corpus.yaml").read_text())
        for corpus in manifest["corpora"].values():
            for dec in corpus["decisions"]:
                xml = (INGESTER_ROOT / dec["golden"]).read_text()
                assert validate_dmn_schema(xml) == []
                errors, _warnings = validate_dmn(xml)
                assert errors == []
