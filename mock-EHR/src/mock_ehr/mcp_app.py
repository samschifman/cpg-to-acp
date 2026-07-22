"""Standalone MCP server for mock-EHR — serves FHIR patient data tools over Streamable HTTP.

The tools proxy to the HAPI FHIR server via REST. Deployed as its own pod
behind the MCP Gateway for governed tool access.
"""

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from mock_ehr.mcp_server import mcp

_mcp_app = mcp.streamable_http_app()


async def health(request):
    return JSONResponse({"status": "UP", "service": "mock-ehr-mcp"})


app = Starlette(
    routes=[Route("/health", health)],
    lifespan=_mcp_app.router.lifespan_context,
)
app.mount("/", _mcp_app)
