"""Plan Composer — core clinical reasoning node.

LLM maps DMN results + recommendations to a PlanningBrief.
Assigns FHIR codes via terminology lookup, populates workflow
context for future BPMN generation.
"""

import json
import logging
from typing import Any

import mlflow
from langchain_openai import ChatOpenAI

from acp_writer.output import write_artifact
from acp_writer.planning_brief import PlanningBrief
from acp_writer.prompts.plan_composer import PLAN_COMPOSER_SYSTEM, PLAN_COMPOSER_USER
from acp_writer.state import CarePlanComposerState

logger = logging.getLogger(__name__)


def _get_llm(state: dict) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=f"{state.get('litellm_url', 'http://localhost:4000')}/v1",
        api_key=state.get("llm_api_key", "sk-change-me"),
        model=state.get("llm_model", "default"),
    )


def _format_conditions(condition_codes: list[dict]) -> str:
    if not condition_codes:
        return "No conditions identified."
    lines = []
    for c in condition_codes:
        display = c.get("display", c.get("code", "unknown"))
        system = c.get("system", "")
        code = c.get("code", "")
        lines.append(f"- {display} ({system}|{code})")
    return "\n".join(lines)


def _format_dmn_results(dmn_results: list[dict]) -> str:
    if not dmn_results:
        return "No DMN decisions evaluated."
    return json.dumps(dmn_results, indent=2, default=str)


def _format_recommendations(recommendations: list[dict]) -> str:
    if not recommendations:
        return "No recommendations retrieved."
    summary = []
    for rec in recommendations:
        cert = rec.get("certainty", {}) or {}
        strength = cert.get("strength", "ungraded") if cert else "ungraded"
        summary.append({
            "id": rec.get("id"),
            "title": rec.get("title"),
            "content": rec.get("content"),
            "type": rec.get("recommendation_type"),
            "strength": strength,
            "source_cpg": rec.get("source_cpg"),
            "remarks": rec.get("remarks"),
        })
    return json.dumps(summary, indent=2)


def _format_demographics(demographics: dict) -> str:
    if not demographics:
        return "Unknown"
    parts = []
    if demographics.get("name"):
        parts.append(demographics["name"])
    if demographics.get("gender"):
        parts.append(demographics["gender"])
    if demographics.get("birth_date"):
        parts.append(f"DOB: {demographics['birth_date']}")
    return ", ".join(parts) if parts else "Unknown"


def _parse_brief_from_response(content: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines) - 1
        if lines[-1].strip() == "```":
            end = len(lines) - 1
        text = "\n".join(lines[start:end])
    return json.loads(text)


@mlflow.trace(name="plan_composer")
def plan_composer(state: CarePlanComposerState) -> dict:
    """Map decisions + recommendations → PlanningBrief."""
    patient_ref = state.get("patient_reference", "Patient/unknown")
    demographics = state.get("patient_demographics", {})
    condition_codes = state.get("condition_codes", [])
    dmn_results = state.get("dmn_results", [])
    recommendations = state.get("recommendations", [])
    applicable_cpgs = state.get("applicable_cpgs", [])
    feedback = state.get("brief_review_feedback", "")
    output_dir = state.get("output_dir", "")

    cpg_ids = [c.get("cpg_id", c) if isinstance(c, dict) else c for c in applicable_cpgs]

    feedback_text = ""
    if feedback:
        feedback_text = f"\n## Reviewer Feedback (address these issues)\n{feedback}"

    user_prompt = PLAN_COMPOSER_USER.format(
        patient_reference=patient_ref,
        demographics=_format_demographics(demographics),
        conditions=_format_conditions(condition_codes),
        dmn_results=_format_dmn_results(dmn_results),
        recommendations=_format_recommendations(recommendations),
        applicable_cpgs=json.dumps(cpg_ids),
        dmn_audit_trail=json.dumps(dmn_results, default=str),
        feedback=feedback_text,
    )

    llm = _get_llm(state)
    logger.info("Invoking Plan Composer LLM")

    response = llm.invoke([
        {"role": "system", "content": PLAN_COMPOSER_SYSTEM},
        {"role": "user", "content": user_prompt},
    ])

    try:
        brief_data = _parse_brief_from_response(response.content)
        brief = PlanningBrief.model_validate(brief_data)
        brief_dict = brief.model_dump(mode="json")

        if output_dir:
            write_artifact(output_dir, "planning-brief.json", brief_dict)

        logger.info(
            "Planning Brief: %d goals, %d activities, %d conflicts",
            len(brief.goals),
            len(brief.activities),
            len(brief.conflicts),
        )

        return {
            "planning_brief": brief_dict,
            "brief_review_feedback": "",
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to parse Planning Brief from LLM response: %s", e)
        logger.debug("Raw response: %s", response.content[:500])
        return {
            "planning_brief": {
                "patient_reference": patient_ref,
                "applicable_cpgs": cpg_ids,
                "goals": [],
                "activities": [],
                "review_status": "flagged",
                "review_feedback": f"LLM response parse error: {e}",
            },
            "brief_review_feedback": "",
        }
