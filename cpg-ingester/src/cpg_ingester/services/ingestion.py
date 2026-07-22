"""Ingestion pod service — Docling PDF parsing.

Produces: parse_result_ref (stores markdown + docling_json in MinIO).
Security profile: filesystem + ML models, no external network.
"""

import logging
import os
import tempfile
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, UploadFile

from cpg_contracts import get_artifact_store, post_callback, store_artifact
from cpg_ingester.nodes.docling_agent import docling_agent

logger = logging.getLogger(__name__)

app = FastAPI(title="cpg-ingester-ingestion", version="0.1.0")
_store = get_artifact_store()


@app.get("/health")
def health():
    return {"status": "UP", "service": "ingestion"}


@app.post("/api/v1/parse")
async def parse_pdf(file: UploadFile = File(...)):
    """Parse a CPG PDF into markdown and Docling JSON (sync)."""
    result = _do_parse(file)
    return result


@app.post("/api/v1/parse-async")
async def parse_pdf_async(
    file: UploadFile = File(...),
    callback_url: str = Form(""),
    process_instance_id: str = Form(""),
    background_tasks: BackgroundTasks = None,
):
    """Async version: accept immediately, parse in background, POST callback."""
    pdf_bytes = await file.read()
    filename = file.filename or "input.pdf"
    background_tasks.add_task(
        _run_parse_background, pdf_bytes, filename, callback_url, process_instance_id
    )
    return {"status": "accepted"}


def _do_parse(file_or_bytes, filename="input.pdf"):
    """Run Docling parsing. Used by both sync and async endpoints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, filename)
        if isinstance(file_or_bytes, bytes):
            with open(pdf_path, "wb") as f:
                f.write(file_or_bytes)
        else:
            import asyncio
            loop = asyncio.get_event_loop()
            data = loop.run_until_complete(file_or_bytes.read())
            with open(pdf_path, "wb") as f:
                f.write(data)

        output_dir = os.path.join(tmpdir, "output")
        os.makedirs(output_dir)

        result = docling_agent({
            "pdf_path": pdf_path,
            "output_dir": output_dir,
        })

        parse_output = {
            "markdown": result.get("markdown", ""),
            "docling_json": result.get("docling_json", {}),
        }

        _, ref = store_artifact(_store, f"{uuid4()}/parse_result.json", parse_output)
        if ref:
            return {"parse_result_ref": ref}
        return parse_output


def _run_parse_background(
    pdf_bytes: bytes, filename: str, callback_url: str, process_instance_id: str
):
    try:
        result = _do_parse(pdf_bytes, filename)
    except Exception as e:
        logger.error("Parse background task failed: %s", e)
        result = {"error": str(e)}

    post_callback(callback_url, process_instance_id, "parse-done", result)
