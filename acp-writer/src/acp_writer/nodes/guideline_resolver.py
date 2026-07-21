"""Guideline Resolver — match patient conditions to registered CPGs and DMN models.

Matches patient condition codes against CPG scope text, identifies
applicable DMN models, and builds a dependency graph from
DecisionModelSummary.modifies for topological execution order.
"""

import logging
from typing import Any

import mlflow

from acp_writer.state import CarePlanComposerState

logger = logging.getLogger(__name__)

SNOMED_SYSTEM = "http://snomed.info/sct"
ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm"


def _condition_matches_scope(condition_codes: list[dict], scope: str | None) -> bool:
    """Check if any patient condition code or display matches the CPG scope text."""
    if not scope:
        return True
    scope_lower = scope.lower()
    for code_entry in condition_codes:
        display = code_entry.get("display", "").lower()
        if display and display in scope_lower:
            return True
        for keyword in display.split():
            if len(keyword) > 3 and keyword in scope_lower:
                return True
    return False


def _build_dependency_graph(
    models: list[dict[str, Any]],
) -> list[list[str]]:
    """Build topological order from model dependency graph.

    Uses DecisionModelSummary.modifies to determine which models
    depend on others. Returns a list of lists — each inner list
    is a level that can run in parallel.
    """
    model_ids = {m["id"] for m in models}
    deps: dict[str, set[str]] = {m["id"]: set() for m in models}

    for model in models:
        modifies = model.get("modifies") or []
        for target_id in modifies:
            if target_id in model_ids:
                deps[target_id].add(model["id"])

    levels: list[list[str]] = []
    remaining = dict(deps)
    resolved: set[str] = set()

    while remaining:
        level = [
            mid for mid, dep_set in remaining.items()
            if dep_set.issubset(resolved)
        ]
        if not level:
            logger.warning("Circular dependency detected, breaking cycle with remaining: %s", list(remaining.keys()))
            level = list(remaining.keys())
        levels.append(sorted(level))
        resolved.update(level)
        for mid in level:
            del remaining[mid]

    return levels


@mlflow.trace(name="guideline_resolver")
def guideline_resolver(state: CarePlanComposerState) -> dict:
    """Match patient conditions to registered CPGs and DMN models."""
    logger.info("── Guideline Resolver ──")
    from acp_writer.api import _dynamic_models, _guidelines_store

    condition_codes = state.get("condition_codes", [])
    if not condition_codes:
        logger.warning("No condition codes to match — skipping guideline resolution")
        return {
            "applicable_cpgs": [],
            "applicable_dmn_models": [],
            "dmn_dependency_graph": [],
        }

    all_guidelines = _guidelines_store.list_all()
    applicable_cpgs = []
    applicable_cpg_ids: set[str] = set()

    for guideline in all_guidelines:
        if _condition_matches_scope(condition_codes, guideline.scope):
            applicable_cpgs.append(guideline.model_dump(mode="json"))
            applicable_cpg_ids.add(guideline.cpg_id)
            logger.info("Matched CPG: %s (%s)", guideline.title, guideline.cpg_id)

    if not applicable_cpgs:
        logger.info("No CPGs matched patient conditions")
        return {
            "applicable_cpgs": [],
            "applicable_dmn_models": [],
            "dmn_dependency_graph": [],
        }

    all_models = list(_dynamic_models.values())
    applicable_models = []

    for model_entry in all_models:
        summary = model_entry["summary"]
        if summary.source_cpg and summary.source_cpg in applicable_cpg_ids:
            applicable_models.append(summary.model_dump(mode="json"))
        elif not summary.source_cpg:
            applicable_models.append(summary.model_dump(mode="json"))

    if not applicable_models:
        logger.info("No DMN models matched applicable CPGs — using all deployed models")
        applicable_models = [
            m["summary"].model_dump(mode="json") for m in all_models
        ]

    dependency_graph = _build_dependency_graph(applicable_models)

    logger.info(
        "Resolved: %d CPGs, %d DMN models, %d execution levels",
        len(applicable_cpgs),
        len(applicable_models),
        len(dependency_graph),
    )

    return {
        "applicable_cpgs": applicable_cpgs,
        "applicable_dmn_models": applicable_models,
        "dmn_dependency_graph": dependency_graph,
    }
