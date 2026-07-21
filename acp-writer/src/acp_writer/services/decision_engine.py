"""Decision Engine pod service — DMN Executor proxy to Kogito.

Security profile: Kogito runtime access only.
"""

import logging

from fastapi import FastAPI, Request

from acp_writer.nodes.dmn_executor import dmn_executor

logger = logging.getLogger(__name__)

app = FastAPI(title="acp-writer-decision-engine", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "UP", "service": "decision-engine"}


@app.post("/api/v1/execute")
async def execute(request: Request):
    """Execute DMN models against patient data."""
    data = await request.json()
    state = {
        "ips_bundle": data.get("ips_bundle", {}),
        "applicable_dmn_models": data.get("applicable_dmn_models", []),
        "dmn_dependency_graph": data.get("dmn_dependency_graph", []),
    }
    result = dmn_executor(state)
    return {"dmn_results": result.get("dmn_results", [])}
