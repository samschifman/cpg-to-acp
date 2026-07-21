"""FastAPI web UI for acp-writer care plan review and approval."""

import json
import logging
import os
import uuid
from pathlib import Path
from threading import Thread

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

app = FastAPI(title="ACP Writer UI")

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
SAMPLE_DATA_DIR = PROJECT_ROOT / "mock-EHR" / "data"
FIXTURES_DIR = PROJECT_ROOT / "shared" / "tests" / "fixtures"

_pending_runs: dict[str, dict] = {}


def _run_pipeline_background(run_id: str, ips_bundle: dict):
    """Run the pipeline in a background thread."""
    try:
        import acp_writer.api as api_module
        from acp_writer.pipeline import build_pipeline

        graph = build_pipeline()
        compiled = graph.compile()

        result = compiled.invoke({
            "ips_bundle": ips_bundle,
            "run_id": run_id,
            "output_dir": f"output/{run_id}",
            "litellm_url": os.environ.get("LITELLM_URL", "http://localhost:4000"),
            "llm_model": os.environ.get("LLM_MODEL", "default"),
            "llm_api_key": os.environ.get("LLM_API_KEY", "sk-change-me"),
        })

        careplan_id = result.get("careplan_id", "")
        _pending_runs[run_id] = {
            "status": "complete",
            "careplan_id": careplan_id,
            "planning_brief": result.get("planning_brief", {}),
        }
        logger.info("Pipeline complete for run %s -> careplan %s", run_id, careplan_id)

    except Exception as e:
        logger.error("Pipeline failed for run %s: %s", run_id, e)
        _pending_runs[run_id] = {"status": "error", "error": str(e)}


def _setup_sample_data():
    """Load sample CPG data if not already registered."""
    import acp_writer.api as api_module
    from acp_writer.api import _dynamic_models, _parse_dmn_metadata
    from cpg_contracts import CPGMetadata, RecommendationBundle

    if api_module._guidelines_store.count() > 0:
        return

    fixtures_file = FIXTURES_DIR / "sample-recommendations.json"
    if not fixtures_file.exists():
        logger.warning("Sample fixtures not found at %s", fixtures_file)
        return

    data = json.loads(fixtures_file.read_text())
    meta = CPGMetadata.model_validate(data["metadata"])
    api_module._guidelines_store.register(meta)

    dmn_dir = PROJECT_ROOT / "cpg-ingester" / "data" / "golden"
    for f in ["treatment-recommendation.dmn", "monitoring-plan.dmn"]:
        dmn_path = dmn_dir / f
        if dmn_path.exists():
            xml = dmn_path.read_text()
            s = _parse_dmn_metadata(xml)
            _dynamic_models[s.id] = {"summary": s, "dmn_xml": xml}

    bundle = RecommendationBundle.model_validate(data["recommendation_bundle"])
    api_module._vector_store.add_batch(bundle.recommendations)
    logger.info("Loaded sample data: 1 CPG, %d recommendations, 2 DMN models", len(bundle.recommendations))


@app.on_event("startup")
async def startup():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    _setup_sample_data()


@app.get("/", response_class=HTMLResponse)
async def submit_page(request: Request):
    import acp_writer.api as api_module
    from acp_writer.api import _dynamic_models
    guidelines = [g.model_dump(mode="json") for g in api_module._guidelines_store.list_all()]
    return templates.TemplateResponse(request, "submit.html", {
        "error": request.query_params.get("error"),
        "guidelines": guidelines,
        "models_deployed": len(_dynamic_models),
        "recs_ingested": api_module._vector_store.count(),
    })


@app.post("/submit")
async def submit_bundle(request: Request, bundle_file: UploadFile = File(...)):
    content = await bundle_file.read()
    try:
        ips_bundle = json.loads(content)
    except json.JSONDecodeError:
        return templates.TemplateResponse(
            request, "submit.html", {"error": "Invalid JSON file"}, status_code=400
        )

    if ips_bundle.get("resourceType") != "Bundle":
        return templates.TemplateResponse(
            request, "submit.html", {"error": "File must be a FHIR Bundle"}, status_code=400
        )

    run_id = str(uuid.uuid4())[:8]
    _pending_runs[run_id] = {"status": "processing"}

    thread = Thread(target=_run_pipeline_background, args=(run_id, ips_bundle), daemon=True)
    thread.start()

    return templates.TemplateResponse(request, "processing.html", {"run_id": run_id})


@app.post("/submit-sample")
async def submit_sample(request: Request, sample: str = Form(...)):
    filename = f"patient-bundle-{sample}.json"
    path = SAMPLE_DATA_DIR / filename
    if not path.exists():
        return templates.TemplateResponse(
            request, "submit.html", {"error": f"Sample '{sample}' not found"}, status_code=404
        )

    ips_bundle = json.loads(path.read_text())
    run_id = str(uuid.uuid4())[:8]
    _pending_runs[run_id] = {"status": "processing"}

    thread = Thread(target=_run_pipeline_background, args=(run_id, ips_bundle), daemon=True)
    thread.start()

    return templates.TemplateResponse(request, "processing.html", {"run_id": run_id})


@app.get("/plans/{run_id}/poll")
async def poll_run(run_id: str):
    run = _pending_runs.get(run_id, {})
    if run.get("status") == "complete":
        careplan_id = run.get("careplan_id", "")
        if careplan_id:
            return RedirectResponse(url=f"/ui/plans/{careplan_id}", status_code=303)
    elif run.get("status") == "error":
        return RedirectResponse(url=f"/ui/?error={run.get('error', 'unknown')}", status_code=303)

    return HTMLResponse(
        f'<html><head><meta http-equiv="refresh" content="5;url=/ui/plans/{run_id}/poll">'
        f'</head><body>Still processing run {run_id}...</body></html>'
    )


@app.get("/plans", response_class=HTMLResponse)
async def plans_list(request: Request):
    from acp_writer.nodes.fhir_server_writer import list_care_plans
    plans = list_care_plans()
    return templates.TemplateResponse(request, "plans.html", {"plans": plans})


@app.get("/plans/{careplan_id}", response_class=HTMLResponse)
async def plan_review(request: Request, careplan_id: str):
    from acp_writer.nodes.fhir_server_writer import get_care_plan

    cp = get_care_plan(careplan_id)
    if not cp:
        return HTMLResponse("<h1>Care plan not found</h1>", status_code=404)

    bundle = cp.get("bundle", {})
    entries = bundle.get("entry", [])
    resource_types: dict[str, int] = {}
    for entry in entries:
        rt = entry.get("resource", {}).get("resourceType", "unknown")
        resource_types[rt] = resource_types.get(rt, 0) + 1

    brief = None
    for run in _pending_runs.values():
        if run.get("careplan_id") == careplan_id:
            brief = run.get("planning_brief")
            break

    return templates.TemplateResponse(request, "review.html", {
        "plan_id": careplan_id,
        "patient_ref": cp.get("patient_reference", "unknown"),
        "status": cp.get("status", "unknown"),
        "brief": brief,
        "entry_count": len(entries),
        "bundle_type": bundle.get("type", "unknown"),
        "resources": resource_types,
        "fhir_json": json.dumps(bundle, indent=2, default=str),
    })


@app.post("/plans/{careplan_id}/approve")
async def approve(careplan_id: str, clinician: str = Form("")):
    from acp_writer.nodes.fhir_server_writer import approve_care_plan
    approve_care_plan(careplan_id, clinician=clinician or "Clinician")
    return RedirectResponse(url=f"/ui/plans/{careplan_id}", status_code=303)


@app.post("/plans/{careplan_id}/reject")
async def reject(careplan_id: str, reason: str = Form("")):
    from acp_writer.nodes.fhir_server_writer import reject_care_plan
    reject_care_plan(careplan_id, reason=reason or "No reason provided")
    return RedirectResponse(url=f"/ui/plans/{careplan_id}", status_code=303)
