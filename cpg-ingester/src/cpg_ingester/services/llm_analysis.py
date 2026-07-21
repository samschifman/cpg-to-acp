"""LLM Analysis pod service — all LLM-calling nodes with in-process LangGraph review loops.

Security profile: LLM inference endpoint only (via MaaS on OpenShift).
Runs structure analysis, item identification with classification review,
metadata extraction, and DMN/Rec generation with review loops.
"""

import logging
import os
import tempfile

from fastapi import FastAPI, Request

from cpg_ingester.nodes.content_filter import content_filter
from cpg_ingester.nodes.item_identifier import item_identifier
from cpg_ingester.nodes.classification_reviewer import classification_reviewer
from cpg_ingester.nodes.metadata_extractor import metadata_extractor
from cpg_ingester.nodes.structure_analyzer import structure_analyzer

logger = logging.getLogger(__name__)

app = FastAPI(title="cpg-ingester-llm-analysis", version="0.1.0")

MAX_CLASSIFICATION_REVIEWS = 2

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LLM_MODEL = os.environ.get("LLM_MODEL", "default")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "sk-change-me")


@app.get("/health")
def health():
    return {"status": "UP", "service": "llm-analysis"}


@app.post("/api/v1/analyze")
async def analyze(request: Request):
    """Run the full LLM analysis phase: structure -> filter -> identify -> review -> metadata -> generate."""
    data = await request.json()

    with tempfile.TemporaryDirectory() as output_dir:
        state = {
            "markdown": data.get("markdown", ""),
            "docling_json": data.get("docling_json", {}),
            "output_dir": output_dir,
            "litellm_url": LITELLM_URL,
            "llm_model": LLM_MODEL,
            "llm_api_key": LLM_API_KEY,
        }

        updates = structure_analyzer(state)
        state.update(updates)

        updates = content_filter(state)
        state.update(updates)

        for _ in range(MAX_CLASSIFICATION_REVIEWS + 1):
            updates = item_identifier(state)
            state.update(updates)

            updates = classification_reviewer(state)
            state.update(updates)

            if not state.get("classification_review_feedback"):
                break
            if state.get("classification_review_count", 0) >= MAX_CLASSIFICATION_REVIEWS:
                break

        updates = metadata_extractor(state)
        state.update(updates)

        from cpg_ingester.pipeline import _generate_all
        updates = _generate_all(state)
        state.update(updates)

        return {
            "section_map": state.get("section_map", []),
            "abbreviations": state.get("abbreviations", {}),
            "grading_definitions": state.get("grading_definitions", ""),
            "archetype": state.get("archetype", ""),
            "item_manifest": state.get("item_manifest", []),
            "cpg_metadata": state.get("cpg_metadata", {}),
            "dmn_results": state.get("dmn_results", []),
            "recommendation_results": state.get("recommendation_results", []),
        }
