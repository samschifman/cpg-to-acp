"""FHIR Generation pod service — Bundle Generator + validators.

Security profile: terminology API access + LLM inference (bundle generation).
"""

import logging
import os

from fastapi import FastAPI, Request

from acp_writer.nodes.fhir_bundle_generator import fhir_bundle_generator
from acp_writer.nodes.terminology_validator import terminology_validator
from acp_writer.nodes.fhir_syntax_validator import fhir_syntax_validator

logger = logging.getLogger(__name__)

app = FastAPI(title="acp-writer-fhir-generation", version="0.1.0")

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LLM_MODEL = os.environ.get("LLM_MODEL", "default")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "sk-change-me")


@app.get("/health")
def health():
    return {"status": "UP", "service": "fhir-generation"}


@app.post("/api/v1/generate-bundle")
async def generate_bundle(request: Request):
    """Generate FHIR Bundle from Planning Brief, then validate."""
    data = await request.json()
    state = {
        "planning_brief": data.get("planning_brief", {}),
        "patient_demographics": data.get("patient_demographics", {}),
        "fhir_review_feedback": data.get("fhir_review_feedback", ""),
        "litellm_url": LITELLM_URL,
        "llm_model": LLM_MODEL,
        "llm_api_key": LLM_API_KEY,
    }

    gen_result = fhir_bundle_generator(state)
    state.update(gen_result)

    term_result = terminology_validator(state)
    syntax_result = fhir_syntax_validator(state)

    return {
        "fhir_bundle": state.get("fhir_bundle", {}),
        "terminology_issues": term_result.get("terminology_issues", []),
        "syntax_errors": syntax_result.get("syntax_errors", []),
    }
