"""Tests for the semantic golden-diff tool and its DMN model parser."""

import sys
from pathlib import Path

import pytest

# DMN benchmark lives in tests/benchmarks/dmn (non-package); import by bare name.
_BENCH = Path(__file__).parent / "benchmarks" / "dmn"
sys.path.insert(0, str(_BENCH))

from dmn_diff import diff_models
from dmn_model import (
    UNIVERSAL,
    Interval,
    ValueSet,
    normalize_output,
    normalize_unary,
    parse_dmn,
)

GOLDEN_DIR = Path(__file__).parent.parent / "data" / "golden"
TREATMENT = (GOLDEN_DIR / "treatment-recommendation.dmn").read_text()
MONITORING = (GOLDEN_DIR / "monitoring-plan.dmn").read_text()


class TestNormalizeUnary:
    def test_universal(self):
        assert normalize_unary("-") is UNIVERSAL
        assert normalize_unary("") is UNIVERSAL

    def test_comparison_to_interval(self):
        iv = normalize_unary(">= 140")
        assert isinstance(iv, Interval)
        assert iv.lo == 140 and iv.lo_inc and iv.hi == float("inf")

    def test_range_and_conjunction_equivalent(self):
        # [140..180) must equal ">= 140 and < 180"
        a = normalize_unary("[140..180)")
        b = normalize_unary(">= 140 and < 180")
        assert isinstance(a, Interval) and isinstance(b, Interval)
        assert a.bounds_equal(b)

    def test_entity_style_comparison(self):
        # lxml decodes &lt; before we see it, but confirm the operator parses
        assert normalize_unary("< 130").hi == 130

    def test_value_set(self):
        vs = normalize_unary('"A","B"')
        assert isinstance(vs, ValueSet)
        assert vs.values == frozenset({"A", "B"})

    def test_boolean_and_string(self):
        assert normalize_unary("true") is True
        assert normalize_unary('"Start medication"') == "Start medication"


class TestNormalizeOutput:
    def test_strip_quotes(self):
        assert normalize_output('"Lisinopril"') == "Lisinopril"

    def test_number_and_bool_and_null(self):
        assert normalize_output("4") == 4
        assert normalize_output("true") is True
        assert normalize_output("null") is None

    def test_dash(self):
        assert normalize_output('"-"') == "-"
        assert normalize_output("-") == "-"


class TestParse:
    def test_parses_golden(self):
        m = parse_dmn(TREATMENT)
        assert m.name == "Treatment Recommendation"
        assert "Systolic BP" in m.inputs
        assert len(m.decisions) == 1
        dec = m.decisions[0]
        assert dec.hit_policy == "FIRST"
        assert len(dec.rules) == 9
        assert dec.input_columns == ["Systolic BP", "Has Diabetes", "Has Kidney Disease"]


class TestDiffModels:
    def test_identical_scores_one(self):
        report = diff_models(TREATMENT, TREATMENT)
        assert report["structural_f1"] == 1.0
        assert report["structural_recall"] == 1.0
        assert report["structural_precision"] == 1.0
        assert report["threshold_exactness"] == 1.0

    def test_serialized_differently_still_one(self):
        # The diff is namespace-agnostic: a legacy DMN 1.3 serialization of the
        # same model must still score 1.0 against the migrated 1.4 golden.
        variant = TREATMENT.replace(
            "https://www.omg.org/spec/DMN/20211108/MODEL/",
            "https://www.omg.org/spec/DMN/20191111/MODEL/",
        ).replace(
            "https://www.omg.org/spec/DMN/20211108/FEEL/",
            "https://www.omg.org/spec/DMN/20191111/FEEL/",
        )
        report = diff_models(TREATMENT, variant)
        assert report["structural_f1"] == 1.0

    def test_threshold_off_by_five_keeps_f1_drops_exactness(self):
        # Shift rule 1's ">= 140" to ">= 145": rule still overlaps -> matched,
        # F1 stays 1.0, but threshold-exactness drops and a delta is reported.
        mutated = TREATMENT.replace(
            "<text><![CDATA[>= 140]]></text>", "<text><![CDATA[>= 145]]></text>"
        )
        report = diff_models(TREATMENT, mutated)
        assert report["structural_f1"] == 1.0
        assert report["threshold_exact_rules"] == report["matched_rules"] - 1
        deltas = report["decisions"][0]["threshold_deltas"]
        assert len(deltas) == 1

    def test_dropped_rule_lowers_recall(self):
        mutated = TREATMENT.replace(
            """      <!-- Rule 5: SBP 130-139, No Diabetes, No Kidney Disease -->
      <rule id="rule_5">
        <description>Stage 1 hypertension without comorbidities - lifestyle only</description>
        <inputEntry id="r5_ie1"><text><![CDATA[[130..139]]]></text></inputEntry>
        <inputEntry id="r5_ie2"><text><![CDATA[false]]></text></inputEntry>
        <inputEntry id="r5_ie3"><text><![CDATA[false]]></text></inputEntry>
        <outputEntry id="r5_oe1"><text><![CDATA["Lifestyle modification only"]]></text></outputEntry>
        <outputEntry id="r5_oe2"><text><![CDATA["-"]]></text></outputEntry>
        <outputEntry id="r5_oe3"><text><![CDATA["-"]]></text></outputEntry>
        <outputEntry id="r5_oe4"><text><![CDATA[8]]></text></outputEntry>
      </rule>
""", "")
        report = diff_models(TREATMENT, mutated)
        assert report["structural_recall"] < 1.0
        assert report["generated_rule_count"] == 8
        assert len(report["decisions"][0]["missing_rules"]) == 1

    def test_extra_rule_lowers_precision(self):
        extra = """      <rule id="rule_extra">
        <inputEntry id="rx_ie1"><text>>= 200</text></inputEntry>
        <inputEntry id="rx_ie2"><text>-</text></inputEntry>
        <inputEntry id="rx_ie3"><text>-</text></inputEntry>
        <outputEntry id="rx_oe1"><text>"Emergency referral"</text></outputEntry>
        <outputEntry id="rx_oe2"><text>"-"</text></outputEntry>
        <outputEntry id="rx_oe3"><text>"-"</text></outputEntry>
        <outputEntry id="rx_oe4"><text>1</text></outputEntry>
      </rule>
    </decisionTable>"""
        mutated = TREATMENT.replace("    </decisionTable>", extra)
        report = diff_models(TREATMENT, mutated)
        assert report["structural_precision"] < 1.0
        assert report["generated_rule_count"] == 10
        assert len(report["decisions"][0]["extra_rules"]) == 1

    def test_wrong_output_reported_as_output_delta(self):
        mutated = MONITORING.replace(
            '<outputEntry id="r1_oe1"><text><![CDATA["Basic Metabolic Panel"]]></text></outputEntry>',
            '<outputEntry id="r1_oe1"><text><![CDATA["No labs required"]]></text></outputEntry>',
        )
        report = diff_models(MONITORING, mutated)
        # Same conditions -> rule matched, but output differs.
        assert report["structural_f1"] == 1.0
        assert len(report["decisions"][0]["output_deltas"]) == 1
