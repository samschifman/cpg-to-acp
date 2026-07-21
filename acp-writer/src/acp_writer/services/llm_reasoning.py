"""LLM Reasoning pod service — Guideline Resolver, Recommendation Retriever,
Plan Composer with Brief Reviewer loop, FHIR Semantic Reviewer.

Security profile: LLM inference + vector store, no FHIR server access.
"""

import logging
import os

from fastapi import FastAPI, Request

from acp_writer.nodes.guideline_resolver import guideline_resolver
from acp_writer.nodes.recommendation_retriever import recommendation_retriever
from acp_writer.nodes.plan_composer import plan_composer
from acp_writer.nodes.brief_reviewer import brief_reviewer
from acp_writer.nodes.fhir_semantic_reviewer import fhir_semantic_reviewer
from acp_writer.pipeline import MAX_BRIEF_REVIEWS

logger = logging.getLogger(__name__)

app = FastAPI(title="acp-writer-llm-reasoning", version="0.1.0")

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LLM_MODEL = os.environ.get("LLM_MODEL", "default")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "sk-change-me")


@app.get("/health")
def health():
    return {"status": "UP", "service": "llm-reasoning"}


@app.post("/api/v1/resolve")
async def resolve(request: Request):
    """Resolve applicable guidelines for patient conditions."""
    data = await request.json()
    state = {
        "condition_codes": data.get("condition_codes", []),
        "litellm_url": LITELLM_URL,
        "llm_model": LLM_MODEL,
        "llm_api_key": LLM_API_KEY,
    }
    result = guideline_resolver(state)
    return {
        "applicable_cpgs": result.get("applicable_cpgs", []),
        "applicable_dmn_models": result.get("applicable_dmn_models", []),
        "dmn_dependency_graph": result.get("dmn_dependency_graph", []),
    }


@app.post("/api/v1/retrieve")
async def retrieve(request: Request):
    """Retrieve recommendations from vector store."""
    data = await request.json()
    state = {
        "condition_codes": data.get("condition_codes", []),
        "dmn_results": data.get("dmn_results", []),
        "applicable_cpgs": data.get("applicable_cpgs", []),
    }
    result = recommendation_retriever(state)
    return {"recommendations": result.get("recommendations", [])}


@app.post("/api/v1/compose")
async def compose(request: Request):
    """Run Plan Composer with Brief Reviewer loop."""
    data = await request.json()
    state = {
        "patient_reference": data.get("patient_reference", ""),
        "patient_demographics": data.get("patient_demographics", {}),
        "condition_codes": data.get("condition_codes", []),
        "medication_codes": data.get("medication_codes", []),
        "allergy_codes": data.get("allergy_codes", []),
        "dmn_results": data.get("dmn_results", []),
        "recommendations": data.get("recommendations", []),
        "applicable_cpgs": data.get("applicable_cpgs", []),
        "litellm_url": LITELLM_URL,
        "llm_model": LLM_MODEL,
        "llm_api_key": LLM_API_KEY,
        "brief_review_count": 0,
        "brief_review_feedback": "",
    }

    for _ in range(MAX_BRIEF_REVIEWS + 1):
        updates = plan_composer(state)
        state.update(updates)

        updates = brief_reviewer(state)
        state.update(updates)

        if not state.get("brief_review_feedback"):
            break
        if state.get("brief_review_count", 0) >= MAX_BRIEF_REVIEWS:
            break

    return {"planning_brief": state.get("planning_brief", {})}


@app.post("/api/v1/review-fhir")
async def review_fhir(request: Request):
    """Run FHIR Semantic Reviewer."""
    data = await request.json()
    state = {
        "fhir_bundle": data.get("fhir_bundle", {}),
        "terminology_issues": data.get("terminology_issues", []),
        "syntax_errors": data.get("syntax_errors", []),
        "fhir_review_count": data.get("fhir_review_count", 0),
        "litellm_url": LITELLM_URL,
        "llm_model": LLM_MODEL,
        "llm_api_key": LLM_API_KEY,
    }
    result = fhir_semantic_reviewer(state)
    return {
        "fhir_review_feedback": result.get("fhir_review_feedback", ""),
        "fhir_review_count": result.get("fhir_review_count", 0),
    }
