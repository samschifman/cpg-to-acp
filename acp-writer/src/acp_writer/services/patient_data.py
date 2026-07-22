"""Patient Data pod service — Condition Scanner + IPS extraction.

Security profile: patient data access, no LLM, no FHIR server.
Produces: ips_bundle_ref (stores original bundle for downstream use by ExecuteDMN).
"""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request

from cpg_contracts import get_phi_store, store_artifact
from acp_writer.nodes.condition_scanner import condition_scanner

logger = logging.getLogger(__name__)

app = FastAPI(title="acp-writer-patient-data", version="0.1.0")
_phi_store = get_phi_store()


@app.get("/health")
def health():
    return {"status": "UP", "service": "patient-data"}


@app.post("/api/v1/scan")
async def scan(request: Request):
    """Extract patient conditions, medications, demographics from IPS Bundle."""
    data = await request.json()
    ips_bundle = data.get("ips_bundle", {})
    result = condition_scanner({"ips_bundle": ips_bundle})

    _, ref = store_artifact(_phi_store, f"{uuid4()}/ips_bundle.json", ips_bundle)
    if ref:
        result["ips_bundle_ref"] = ref

    return result
