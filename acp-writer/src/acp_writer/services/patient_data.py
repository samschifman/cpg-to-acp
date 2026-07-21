"""Patient Data pod service — Condition Scanner + IPS extraction.

Security profile: patient data access, no LLM, no FHIR server.
"""

import logging

from fastapi import FastAPI, Request

from acp_writer.nodes.condition_scanner import condition_scanner

logger = logging.getLogger(__name__)

app = FastAPI(title="acp-writer-patient-data", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "UP", "service": "patient-data"}


@app.post("/api/v1/scan")
async def scan(request: Request):
    """Extract patient conditions, medications, demographics from IPS Bundle."""
    data = await request.json()
    result = condition_scanner({"ips_bundle": data.get("ips_bundle", {})})
    return result
