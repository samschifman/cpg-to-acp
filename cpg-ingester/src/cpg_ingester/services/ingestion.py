"""Ingestion pod service — Docling PDF parsing.

Security profile: filesystem + ML models, no external network.
"""

import logging
import os
import tempfile

from fastapi import FastAPI, File, UploadFile

from cpg_ingester.nodes.docling_agent import docling_agent

logger = logging.getLogger(__name__)

app = FastAPI(title="cpg-ingester-ingestion", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "UP", "service": "ingestion"}


@app.post("/api/v1/parse")
async def parse_pdf(file: UploadFile = File(...)):
    """Parse a CPG PDF into markdown and Docling JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, file.filename or "input.pdf")
        with open(pdf_path, "wb") as f:
            f.write(await file.read())

        output_dir = os.path.join(tmpdir, "output")
        os.makedirs(output_dir)

        result = docling_agent({
            "pdf_path": pdf_path,
            "output_dir": output_dir,
        })

        return {
            "markdown": result.get("markdown", ""),
            "docling_json": result.get("docling_json", {}),
        }
