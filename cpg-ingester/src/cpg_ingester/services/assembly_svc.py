"""Assembly pod service — deterministic cross-reference resolution and integrity checks.

Security profile: no external network, no LLM.
"""

import logging
import tempfile

from fastapi import FastAPI, Request

from cpg_ingester.nodes.assembly import assembly

logger = logging.getLogger(__name__)

app = FastAPI(title="cpg-ingester-assembly", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "UP", "service": "assembly"}


@app.post("/api/v1/assemble")
async def assemble(request: Request):
    """Assemble validated outputs from DMN and Rec generation."""
    data = await request.json()

    with tempfile.TemporaryDirectory() as output_dir:
        state = {
            "cpg_metadata": data.get("cpg_metadata", {}),
            "item_manifest": data.get("item_manifest", []),
            "dmn_results": data.get("dmn_results", []),
            "recommendation_results": data.get("recommendation_results", []),
            "output_dir": output_dir,
        }

        result = assembly(state)

        return {
            "dmn_results": result.get("dmn_results", []),
            "recommendation_results": result.get("recommendation_results", []),
            "escalated_items": result.get("escalated_items", []),
            "assembly_report": result.get("assembly_report", {}),
        }
