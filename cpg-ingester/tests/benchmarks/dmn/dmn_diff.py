"""Semantic golden-diff for DMN: structure-level comparison, not text-level.

Compares a generated DMN against a golden DMN at the level of meaning — input
set, output set, hit policy, and per-rule condition intervals/value-sets — so
that models which serialize differently but decide identically score 1.0, while
a shifted threshold or a dropped/extra rule is surfaced precisely.

Namespace and CDATA tolerance come from :mod:`dmn_model`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import mlflow

from dmn_model import (
    UNIVERSAL,
    DecisionModel,
    DmnModel,
    Interval,
    RuleModel,
    ValueSet,
    parse_dmn,
)


@dataclass
class DecisionDiff:
    """Comparison result for a single decision."""

    decision_name: str
    inputs_match: bool
    outputs_match: bool
    hit_policy_match: bool
    golden_rule_count: int
    generated_rule_count: int
    matched_rules: int
    missing_rules: list = field(default_factory=list)   # golden rules with no match
    extra_rules: list = field(default_factory=list)     # generated rules with no match
    threshold_deltas: list = field(default_factory=list)  # matched rules, differing bounds
    output_deltas: list = field(default_factory=list)   # matched rules, differing outputs
    threshold_exact_rules: int = 0

    @property
    def recall(self) -> float:
        return self.matched_rules / self.golden_rule_count if self.golden_rule_count else 0.0

    @property
    def precision(self) -> float:
        return self.matched_rules / self.generated_rule_count if self.generated_rule_count else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(recall=round(self.recall, 4), precision=round(self.precision, 4),
                 f1=round(self.f1, 4))
        return d


def _cells_overlap(a, b) -> bool:
    """Do two normalized unary-test cells share any value?"""
    if a is UNIVERSAL or b is UNIVERSAL:
        return True
    if isinstance(a, Interval) and isinstance(b, Interval):
        return a.overlaps(b)
    if isinstance(a, ValueSet) and isinstance(b, ValueSet):
        return a.overlaps(b)
    if isinstance(a, ValueSet):
        return _scalar_in_set(b, a)
    if isinstance(b, ValueSet):
        return _scalar_in_set(a, b)
    if isinstance(a, Interval) or isinstance(b, Interval):
        # One interval, one scalar number
        return _scalar_in_interval(b, a) if isinstance(a, Interval) else _scalar_in_interval(a, b)
    return a == b


def _scalar_in_set(scalar, vs: ValueSet) -> bool:
    from dmn_model import _hashable
    return _hashable(scalar) in vs.values


def _scalar_in_interval(scalar, iv: Interval) -> bool:
    if not isinstance(scalar, (int, float)):
        return False
    lo_ok = scalar > iv.lo or (scalar == iv.lo and iv.lo_inc)
    hi_ok = scalar < iv.hi or (scalar == iv.hi and iv.hi_inc)
    return lo_ok and hi_ok


def _cells_bounds_equal(a, b) -> bool:
    """Exact-match test for a matched cell (threshold-exactness)."""
    if a is UNIVERSAL and b is UNIVERSAL:
        return True
    if isinstance(a, Interval) and isinstance(b, Interval):
        return a.bounds_equal(b)
    if isinstance(a, ValueSet) and isinstance(b, ValueSet):
        return a.values == b.values
    return a == b


def _rule_condition_matches(g: RuleModel, x: RuleModel) -> bool:
    """A candidate rule match requires every aligned input cell to overlap."""
    if len(g.inputs) != len(x.inputs):
        return False
    return all(_cells_overlap(a, b) for a, b in zip(g.inputs, x.inputs))


def _rule_exactness(g: RuleModel, x: RuleModel) -> int:
    """Count of input cells whose bounds match exactly (ranking key)."""
    return sum(1 for a, b in zip(g.inputs, x.inputs) if _cells_bounds_equal(a, b))


def diff_decision(golden: DecisionModel, generated: DecisionModel) -> DecisionDiff:
    """Compare one golden decision against one generated decision."""
    inputs_match = (
        [c.lower() for c in golden.input_columns] == [c.lower() for c in generated.input_columns]
        and golden.input_types == generated.input_types
    )
    outputs_match = (
        [c.lower() for c in golden.output_columns] == [c.lower() for c in generated.output_columns]
        and golden.output_types == generated.output_types
    )
    hit_policy_match = golden.hit_policy.upper() == generated.hit_policy.upper()

    diff = DecisionDiff(
        decision_name=golden.name,
        inputs_match=inputs_match,
        outputs_match=outputs_match,
        hit_policy_match=hit_policy_match,
        golden_rule_count=len(golden.rules),
        generated_rule_count=len(generated.rules),
        matched_rules=0,
    )

    # Greedy one-to-one matching: for each golden rule, pick the overlapping
    # generated rule with the most exact-bound cells (then most exact outputs).
    used = set()
    for gi, g in enumerate(golden.rules):
        best, best_score = None, (-1, -1)
        for xi, x in enumerate(generated.rules):
            if xi in used or not _rule_condition_matches(g, x):
                continue
            out_exact = sum(1 for a, b in zip(g.outputs, x.outputs) if a == b)
            score = (_rule_exactness(g, x), out_exact)
            if score > best_score:
                best, best_score = xi, score
        if best is None:
            diff.missing_rules.append({"rule_id": g.rule_id, "inputs": g.raw_inputs,
                                       "outputs": g.raw_outputs})
            continue
        used.add(best)
        diff.matched_rules += 1
        x = generated.rules[best]

        bound_diffs = []
        for col, (a, b) in enumerate(zip(g.inputs, x.inputs)):
            if not _cells_bounds_equal(a, b):
                col_name = golden.input_columns[col] if col < len(golden.input_columns) else str(col)
                bound_diffs.append({"column": col_name,
                                    "golden": g.raw_inputs[col] if col < len(g.raw_inputs) else "",
                                    "generated": x.raw_inputs[col] if col < len(x.raw_inputs) else ""})
        if bound_diffs:
            diff.threshold_deltas.append({"rule_id": g.rule_id, "cells": bound_diffs})
        else:
            diff.threshold_exact_rules += 1

        out_diffs = []
        for col, (a, b) in enumerate(zip(g.outputs, x.outputs)):
            if a != b:
                col_name = golden.output_columns[col] if col < len(golden.output_columns) else str(col)
                out_diffs.append({"column": col_name,
                                  "golden": g.raw_outputs[col] if col < len(g.raw_outputs) else "",
                                  "generated": x.raw_outputs[col] if col < len(x.raw_outputs) else ""})
        if out_diffs:
            diff.output_deltas.append({"rule_id": g.rule_id, "cells": out_diffs})

    for xi, x in enumerate(generated.rules):
        if xi not in used:
            diff.extra_rules.append({"rule_id": x.rule_id, "inputs": x.raw_inputs,
                                     "outputs": x.raw_outputs})

    return diff


@mlflow.trace(name="dmn_golden_diff")
def diff_models(golden_xml: str, generated_xml: str) -> dict:
    """Compare two DMN documents; return a per-decision + aggregate report.

    Decisions are paired by normalized name; if names do not line up (e.g. a
    single-decision file), they are paired positionally as a fallback.
    """
    golden = parse_dmn(golden_xml)
    generated = parse_dmn(generated_xml)

    gen_by_name = {d.name.lower(): d for d in generated.decisions}
    decision_diffs = []
    used_names = set()
    for i, gd in enumerate(golden.decisions):
        match = gen_by_name.get(gd.name.lower())
        if match is None and i < len(generated.decisions):
            match = generated.decisions[i]
        if match is None:
            decision_diffs.append(DecisionDiff(
                decision_name=gd.name, inputs_match=False, outputs_match=False,
                hit_policy_match=False, golden_rule_count=len(gd.rules),
                generated_rule_count=0, matched_rules=0,
                missing_rules=[{"rule_id": r.rule_id, "inputs": r.raw_inputs,
                                "outputs": r.raw_outputs} for r in gd.rules],
            ))
            continue
        used_names.add(match.name.lower())
        decision_diffs.append(diff_decision(gd, match))

    total_golden = sum(d.golden_rule_count for d in decision_diffs)
    total_gen = sum(d.generated_rule_count for d in decision_diffs)
    total_matched = sum(d.matched_rules for d in decision_diffs)
    total_exact = sum(d.threshold_exact_rules for d in decision_diffs)
    recall = total_matched / total_golden if total_golden else 0.0
    precision = total_matched / total_gen if total_gen else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "structural_f1": round(f1, 4),
        "structural_precision": round(precision, 4),
        "structural_recall": round(recall, 4),
        "threshold_exact_rules": total_exact,
        "threshold_exactness": round(total_exact / total_matched, 4) if total_matched else 0.0,
        "golden_rule_count": total_golden,
        "generated_rule_count": total_gen,
        "matched_rules": total_matched,
        "decisions": [d.to_dict() for d in decision_diffs],
    }
