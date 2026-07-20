"""Mock acp-writer receiver for testing cpg-ingester delivery.

Accepts the same API endpoints as acp-writer and writes received
artifacts to a local directory for inspection.

Run standalone:
    python -m tests.mock_receiver [--output-dir ./received] [--port 8082]
"""

import json
import logging
from pathlib import Path

import click
import uvicorn
from fastapi import FastAPI, Request, Response

from cpg_contracts import CPGMetadata, DecisionModelSummary, RecommendationBundle

logger = logging.getLogger(__name__)

app = FastAPI(title="Mock ACP-Writer Receiver")
_output_dir = Path("received")
_counters = {"guidelines": 0, "decisions": 0, "recommendations": 0}


@app.post("/api/v1/guidelines", status_code=201)
async def register_guideline(request: Request):
    body = await request.json()
    metadata = CPGMetadata(**body)
    _output_dir.mkdir(parents=True, exist_ok=True)
    path = _output_dir / f"guideline-{metadata.cpg_id}.json"
    path.write_text(json.dumps(body, indent=2, default=str))
    _counters["guidelines"] += 1
    logger.info("Received guideline: %s → %s", metadata.cpg_id, path)
    return body


@app.post("/api/v1/decisions/models", status_code=201)
async def deploy_decision_model(request: Request):
    content_type = request.headers.get("content-type", "")
    if "xml" in content_type:
        dmn_xml = (await request.body()).decode()
        _output_dir.mkdir(parents=True, exist_ok=True)
        _counters["decisions"] += 1
        path = _output_dir / f"decision-{_counters['decisions']}.dmn"
        path.write_text(dmn_xml)
        logger.info("Received DMN model → %s", path)
        return DecisionModelSummary(
            id=f"mock-{_counters['decisions']}",
            name=f"decision-{_counters['decisions']}",
            inputs=[],
            outputs=[],
        ).model_dump()
    body = await request.json()
    return body


@app.post("/api/v1/knowledge/recommendations/batch", status_code=201)
async def ingest_recommendation_batch(request: Request):
    body = await request.json()
    bundle = RecommendationBundle(**body)
    _output_dir.mkdir(parents=True, exist_ok=True)
    path = _output_dir / f"recommendations-{bundle.source_cpg}.json"
    path.write_text(json.dumps(body, indent=2, default=str))
    _counters["recommendations"] += len(bundle.recommendations)
    logger.info(
        "Received %d recommendations for %s → %s",
        len(bundle.recommendations), bundle.source_cpg, path,
    )
    return {"ingested": len(bundle.recommendations), "source_cpg": bundle.source_cpg}


@app.get("/health")
async def health():
    return {"status": "UP", "received": _counters}


@click.command()
@click.option("--output-dir", type=click.Path(path_type=Path), default=Path("received"))
@click.option("--port", type=int, default=8082)
def main(output_dir: Path, port: int):
    """Run the mock acp-writer receiver."""
    global _output_dir
    _output_dir = output_dir
    logging.basicConfig(level=logging.INFO)
    click.echo(f"Mock acp-writer receiver on port {port}, writing to {output_dir}/")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
