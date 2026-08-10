"""BFF (Backend-for-Frontend) service for the cpg-ingester React UI.

Mediates between the SPA and SonataFlow/MinIO. Each backend dependency
is independently optional — MinIO can be configured without SonataFlow
and vice versa. Endpoints that lack their backing service fall back to
mock data when available.
"""

import logging
import os
from uuid import uuid4

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from cpg_contracts.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)

SONATAFLOW_URL = os.getenv("SONATAFLOW_URL", "")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "")
DATA_INDEX_URL = os.getenv("DATA_INDEX_URL", "")

_artifact_store: ArtifactStore | None = None
if MINIO_ENDPOINT:
    _artifact_store = ArtifactStore(
        endpoint_url=MINIO_ENDPOINT,
        bucket="cpg-uploads",
        access_key=os.getenv("ARTIFACT_STORE_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("ARTIFACT_STORE_SECRET_KEY", "minioadmin"),
    )

app = FastAPI(title="cpg-ingester-bff", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {
        "status": "UP",
        "service": "bff",
        "minio": bool(_artifact_store),
        "sonataflow": bool(SONATAFLOW_URL),
    }


# ---------------------------------------------------------------------------
# MinIO-backed endpoints (upload, artifacts) — registered first so they
# take priority over mock router paths when MinIO is configured
# ---------------------------------------------------------------------------

if _artifact_store:

    @app.post("/api/v1/upload")
    async def upload_cpg(pdf: UploadFile = File(...)):
        run_id = f"run-{uuid4().hex[:8]}"
        key = f"{run_id}/{pdf.filename}"
        content = await pdf.read()
        content_type = pdf.content_type or "application/pdf"
        _artifact_store.put_raw(key, content, content_type)
        logger.info("Uploaded %s (%d bytes) -> %s", pdf.filename, len(content), key)
        # TODO: start SonataFlow workflow with run_id + pdf ref
        return {"runId": run_id}

    @app.get("/api/v1/runs/{run_id}/artifacts/{path:path}")
    def get_artifact(run_id: str, path: str):
        key = f"{run_id}/{path}"
        try:
            data = _artifact_store.get_raw(key)
        except Exception:
            return JSONResponse(status_code=404, content={"error": f"Artifact not found: {key}"})
        return Response(content=data, media_type="application/octet-stream")


# ---------------------------------------------------------------------------
# Mock fallback for SonataFlow-dependent endpoints (runs, reviews).
# Registered after MinIO endpoints so real upload/artifact routes win.
# ---------------------------------------------------------------------------
_mock_mode = False
if not SONATAFLOW_URL:
    try:
        from cpg_ingester.mocks.router import router as mock_router
        app.include_router(mock_router)
        _mock_mode = True
        logger.info("No SONATAFLOW_URL configured — serving mock run/review data")
    except ImportError:
        logger.warning("No SonataFlow configured and mocks package not available")


# ---------------------------------------------------------------------------
# SonataFlow-backed endpoints (runs, reviews) — only when not mocked
# ---------------------------------------------------------------------------

if not _mock_mode:

    @app.get("/api/v1/runs")
    def list_runs():
        # TODO: proxy to SonataFlow / Data Index
        return []

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str):
        # TODO: query Data Index GraphQL + MinIO artifacts
        return {}

    @app.post("/api/v1/runs/{run_id}/review/{gate}")
    async def submit_review(run_id: str, gate: str):
        # TODO: send CloudEvent to SonataFlow
        return {"status": "accepted"}

    @app.post("/api/v1/runs/{run_id}/rerun")
    async def rerun_pipeline(run_id: str):
        # TODO: read original pdf_ref, create new workflow instance
        return {"runId": ""}
