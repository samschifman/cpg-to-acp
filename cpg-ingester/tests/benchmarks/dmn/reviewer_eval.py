"""Reviewer evaluation: seed defects, run the semantic reviewer, score it.

Builds the minimal state the ``dmn_semantic_reviewer`` node expects and invokes
it directly (no subgraph), once per (model, source-section) pair. Clean goldens
must pass (a flag on a clean model is a false escalation); defective variants
should be flagged (recall). Metrics are computed per defect class.

A subset of the corpus is designated *holdout* (never used to drive prompt
tuning in a later phase) to guard against overfitting the reviewer to the
synthetic injectors — see ``config.yaml``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from cpg_ingester.generation import _extract_section_text
from cpg_ingester.nodes.dmn_semantic_reviewer import dmn_semantic_reviewer

from defects import INJECTORS, DefectNotApplicable

logger = logging.getLogger(__name__)


@dataclass
class ReviewerCase:
    """One reviewer invocation and its outcome."""

    decision: str
    kind: str            # "clean" or a defect class
    holdout: bool
    flagged: bool
    discrepancies: list = field(default_factory=list)
    defect_detail: str = ""


def _section_text(markdown: str, heading: str) -> str:
    section_map = [{"heading": heading}]
    return _extract_section_text(markdown, section_map, heading)


def _run_reviewer(dmn_xml: str, name: str, source_text: str, llm_config: dict,
                  output_dir: str) -> list[str]:
    state = {
        "dmn_xml": dmn_xml,
        "item": {"name": name},
        "source_pages": source_text,
        "output_dir": output_dir,
        "semantic_retry_count": 0,
        **llm_config,
    }
    result = dmn_semantic_reviewer(state)
    return result.get("semantic_discrepancies", []) or []


def run_reviewer_suite(corpus: dict, markdown: str, llm_config: dict,
                       output_dir: str, holdout_classes: set[str],
                       repo_root) -> dict:
    """Run the reviewer over clean + defective variants of every golden.

    ``corpus`` is one corpus entry (``corpora.<name>``) from ``corpus.yaml``.
    Returns a metrics dict plus the raw case list.
    """
    cases: list[ReviewerCase] = []

    for dec in corpus.get("decisions", []):
        name = dec["name"]
        heading = dec.get("source_section", {}).get("heading", "")
        source_text = _section_text(markdown, heading)
        if not source_text:
            logger.warning("No source text for '%s' (heading %r) — reviewer eval "
                           "will run with empty source", name, heading)
        golden_xml = (repo_root / dec["golden"]).read_text()

        # Clean model — should NOT be flagged.
        clean_flags = _run_reviewer(golden_xml, name, source_text, llm_config, output_dir)
        cases.append(ReviewerCase(decision=name, kind="clean", holdout=False,
                                  flagged=bool(clean_flags), discrepancies=clean_flags))

        # Defective variants — should be flagged.
        for defect_class, injector in INJECTORS.items():
            try:
                mutated_xml, desc = injector(golden_xml)
            except DefectNotApplicable as e:
                logger.info("Defect %s not applicable to '%s': %s", defect_class, name, e)
                continue
            flags = _run_reviewer(mutated_xml, name, source_text, llm_config, output_dir)
            cases.append(ReviewerCase(
                decision=name, kind=defect_class,
                holdout=defect_class in holdout_classes,
                flagged=bool(flags), discrepancies=flags, defect_detail=desc.detail,
            ))

    return _score(cases)


def _score(cases: list[ReviewerCase]) -> dict:
    defect_cases = [c for c in cases if c.kind != "clean"]
    clean_cases = [c for c in cases if c.kind == "clean"]

    # Per defect-class recall.
    per_class: dict[str, dict] = {}
    for c in defect_cases:
        d = per_class.setdefault(c.kind, {"seeded": 0, "flagged": 0})
        d["seeded"] += 1
        d["flagged"] += int(c.flagged)
    for k, d in per_class.items():
        d["recall"] = round(d["flagged"] / d["seeded"], 4) if d["seeded"] else 0.0

    seeded_total = len(defect_cases)
    caught_total = sum(int(c.flagged) for c in defect_cases)
    clean_flagged = sum(int(c.flagged) for c in clean_cases)

    # Precision over the whole clean+defective set: true flags / all flags.
    all_flags = caught_total + clean_flagged
    precision = round(caught_total / all_flags, 4) if all_flags else 0.0

    def split_metrics(subset):
        seeded = [c for c in subset if c.kind != "clean"]
        n = len(seeded)
        caught = sum(int(c.flagged) for c in seeded)
        return {
            "seeded": n,
            "caught": caught,
            "recall": round(caught / n, 4) if n else 0.0,
            "missed_defect_rate": round((n - caught) / n, 4) if n else 0.0,
        }

    return {
        "overall_recall": round(caught_total / seeded_total, 4) if seeded_total else 0.0,
        "overall_precision": precision,
        "false_escalation_rate": round(clean_flagged / len(clean_cases), 4) if clean_cases else 0.0,
        "missed_defect_rate": round((seeded_total - caught_total) / seeded_total, 4) if seeded_total else 0.0,
        "clean_models": len(clean_cases),
        "clean_flagged": clean_flagged,
        "seeded_defects": seeded_total,
        "caught_defects": caught_total,
        "per_defect_class": per_class,
        "tuning_set": split_metrics([c for c in cases if not c.holdout]),
        "holdout_set": split_metrics([c for c in cases if c.holdout]),
        "cases": [c.__dict__ for c in cases],
    }
