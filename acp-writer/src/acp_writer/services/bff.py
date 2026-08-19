"""BFF for the acp-writer React UI.

When SONATAFLOW_URL is unset (the default), mounts the mock router backed by an
in-memory store — no SonataFlow/MinIO/LLM/DMN/FHIR needed. The SonataFlow-backed
branch is a stub for the real BFF (Jaideep).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from acp_writer.mocks.router import build_router, seed
from acp_writer.mocks.store import Store


def create_app() -> FastAPI:
    sonataflow_url = os.getenv("SONATAFLOW_URL", "")
    cors_origins = os.getenv("BFF_CORS_ORIGINS", "http://localhost:3001").split(",")

    app = FastAPI(title="acp-writer-bff", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    mock_mode = not sonataflow_url
    store = Store()
    app.state.store = store
    app.state.mock_mode = mock_mode

    @app.get("/health")
    def health():
        return {"status": "UP", "service": "acp-writer-bff", "mock": mock_mode}

    if mock_mode:
        seed(store)
        app.include_router(build_router(store))
    else:  # pragma: no cover - real BFF is Jaideep's work (SonataFlow-backed)
        raise NotImplementedError(
            "SonataFlow-backed BFF not implemented in the mock. Unset SONATAFLOW_URL "
            "to run in mock mode."
        )

    return app


app = create_app()
