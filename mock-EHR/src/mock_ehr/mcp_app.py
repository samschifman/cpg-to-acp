"""Standalone MCP server for mock-EHR — serves FHIR patient data tools over Streamable HTTP.

The tools proxy to the HAPI FHIR server via REST. Deployed as its own pod
behind the MCP Gateway for governed tool access.
"""

from fastapi import FastAPI
from mock_ehr.mcp_server import mcp

app = FastAPI(title="mock-ehr-mcp", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "UP", "service": "mock-ehr-mcp"}


app.mount("/", mcp.streamable_http_app())
