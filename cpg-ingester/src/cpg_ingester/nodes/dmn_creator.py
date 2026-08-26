"""DMN Creator — generates DMN 1.4 XML per decision item."""

import logging
import time

import mlflow
from cpg_contracts import content_to_text, get_llm
from cpg_ingester.output import write_artifact
from cpg_ingester.prompts.dmn_creator import DMN_CREATOR_SYSTEM, DMN_CREATOR_USER
from cpg_ingester.reference.dmn_error_patterns import format_error_pattern_hints
from cpg_ingester.reference.dmn_examples import REFERENCE_EXAMPLES

logger = logging.getLogger(__name__)


def _build_feedback(syntax_errors: list, semantic_discrepancies: list,
                    previous_dmn_xml: str) -> str:
    """Assemble repair-mode feedback: previous attempt + all labeled errors.

    Both error kinds are rendered when both are present (no masking), and matched
    known-error patterns are appended so the model gets a concrete fix, not just
    the raw message.
    """
    if not syntax_errors and not semantic_discrepancies:
        return ""

    sections = [
        "PREVIOUS ATTEMPT NEEDS CORRECTION — return a complete, corrected DMN "
        "document (not a diff, not a fragment)."
    ]
    if previous_dmn_xml:
        sections.append("## Previous attempt\n" + previous_dmn_xml)
    if syntax_errors:
        sections.append("## Syntax errors to fix\n"
                        + "\n".join(f"- {e}" for e in syntax_errors))
    if semantic_discrepancies:
        sections.append("## Semantic discrepancies to fix\n"
                        + "\n".join(f"- {d}" for d in semantic_discrepancies))

    hints = format_error_pattern_hints(list(syntax_errors) + list(semantic_discrepancies))
    if hints:
        sections.append("## Known error patterns\n" + hints)

    return "\n\n".join(sections)


def _format_inputs(inputs: list[dict]) -> str:
    lines = []
    for inp in inputs:
        desc = inp.get("description", "")
        lines.append(f"- {inp['name']} ({inp.get('type', 'string')}): {desc}")
    return "\n".join(lines) if lines else "(none specified)"


def _format_outputs(outputs: list) -> str:
    if not outputs:
        return "(none specified)"
    return "\n".join(f"- {o}" for o in outputs)


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines)
    return stripped.strip()


@mlflow.trace(name="dmn_creator")
def dmn_creator(state: dict) -> dict:
    """Generate DMN 1.4 XML for a decision item."""
    logger.info("── DMN Creator ──")
    item = state.get("item", {})
    source_pages = state.get("source_pages", "")
    abbreviations = state.get("abbreviations", {})
    output_dir = state.get("output_dir", "output")
    syntax_errors = state.get("syntax_errors", [])
    semantic_discrepancies = state.get("semantic_discrepancies", [])
    previous_dmn_xml = state.get("dmn_xml", "")

    name = item.get("name", "Unknown Decision")
    description = item.get("description", "")
    category = item.get("category", "treatment")
    hit_policy = item.get("hit_policy", "FIRST")
    inputs = item.get("inputs", [])
    outputs = item.get("outputs", [])

    feedback = _build_feedback(syntax_errors, semantic_discrepancies, previous_dmn_xml)

    abbr_str = "\n".join(f"- {k}: {v}" for k, v in abbreviations.items()) if abbreviations else "(none)"

    llm = get_llm(state)

    logger.info("Calling LLM...")
    t0 = time.time()
    response = llm.invoke([
        {"role": "system", "content": DMN_CREATOR_SYSTEM.format(reference=REFERENCE_EXAMPLES)},
        {"role": "user", "content": DMN_CREATOR_USER.format(
            name=name,
            description=description,
            category=category,
            hit_policy=hit_policy,
            inputs=_format_inputs(inputs),
            outputs=_format_outputs(outputs),
            source_pages=source_pages,
            abbreviations=abbr_str,
            feedback=feedback,
        )},
    ])
    logger.info("LLM responded in %.1fs", time.time() - t0)

    dmn_xml = _strip_markdown_fences(content_to_text(response.content))

    safe_name = name.lower().replace(" ", "-").replace("/", "-")[:50]
    write_artifact(output_dir, f"dmn/{safe_name}.dmn", dmn_xml)

    # Separate budgets: a syntax retry and a semantic retry are counted
    # independently so one loop cannot exhaust the other's budget.
    syntax_retry_count = state.get("syntax_retry_count", 0)
    semantic_retry_count = state.get("semantic_retry_count", 0)
    if syntax_errors:
        syntax_retry_count += 1
    if semantic_discrepancies:
        semantic_retry_count += 1

    logger.info("DMN Creator produced XML for '%s' (%d chars)", name, len(dmn_xml))

    return {
        "dmn_xml": dmn_xml,
        "previous_dmn_xml": previous_dmn_xml,
        "syntax_errors": [],
        "semantic_discrepancies": [],
        "syntax_retry_count": syntax_retry_count,
        "semantic_retry_count": semantic_retry_count,
    }
