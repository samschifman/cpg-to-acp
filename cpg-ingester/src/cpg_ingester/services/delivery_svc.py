"""Delivery pod service — sends artifacts to acp-writer API.

Security profile: acp-writer API access only.
"""

import logging
import os
import tempfile

from fastapi import FastAPI, Request

from cpg_ingester.nodes.delivery import delivery

logger = logging.getLogger(__name__)

app = FastAPI(title="cpg-ingester-delivery", version="0.1.0")

ACP_WRITER_URL = os.environ.get("ACP_WRITER_URL", "")


@app.get("/health")
def health():
    return {"status": "UP", "service": "delivery"}


@app.post("/api/v1/deliver")
async def deliver(request: Request):
    """Deliver assembled artifacts to acp-writer."""
    data = await request.json()

    with tempfile.TemporaryDirectory() as output_dir:
        state = {
            "cpg_metadata": data.get("cpg_metadata", {}),
            "dmn_results": data.get("dmn_results", []),
            "recommendation_results": data.get("recommendation_results", []),
            "escalated_items": data.get("escalated_items", []),
            "assembly_report": data.get("assembly_report", {}),
            "acp_writer_url": data.get("acp_writer_url") or ACP_WRITER_URL,
            "output_dir": output_dir,
        }

        result = delivery(state)

        return {
            "delivery_status": result.get("delivery_status", {}),
        }
