"""FastAPI web UI for cpg-ingester pipeline.

In pod-split mode, the UI does NOT run the pipeline directly. It sends
the PDF to the Ingestion pod, which feeds into the SonataFlow orchestrator.
Run status and artifacts are read from the shared output directory.
"""

import json
import logging
import os
import shutil
import uuid
from pathlib import Path

import click
import requests as http_requests
import uvicorn
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

app = FastAPI(title="CPG Ingester UI")


@app.get("/health")
def health():
    return {"status": "UP", "service": "cpg-ingester-ui"}


OUTPUT_BASE = Path(os.environ.get("OUTPUT_DIR", "output"))
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "")
_active_runs: dict[str, dict] = {}


def _get_runs() -> list[dict]:
    """List all runs from the output directory."""
    runs = []
    if not OUTPUT_BASE.exists():
        return runs

    for run_dir in sorted(OUTPUT_BASE.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        summary_file = run_dir / "run-summary.json"
        run_info = {
            "run_id": run_dir.name,
            "pdf_name": "—",
            "manifest_items": 0,
            "dmn_results": 0,
            "recommendations": 0,
            "escalated_items": 0,
            "complete": summary_file.exists(),
        }
        if summary_file.exists():
            try:
                data = json.loads(summary_file.read_text())
                run_info.update({
                    "pdf_name": Path(data.get("pdf_path", "")).name,
                    "manifest_items": data.get("manifest_items", 0),
                    "dmn_results": data.get("dmn_results", 0),
                    "recommendations": data.get("recommendations", 0),
                    "escalated_items": data.get("escalated_items", 0),
                })
            except (json.JSONDecodeError, KeyError):
                pass
        runs.append(run_info)
    return runs


def _load_json_artifact(run_dir: Path, name: str) -> dict | list | None:
    path = run_dir / name
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _list_artifacts(run_dir: Path) -> list[dict]:
    if not run_dir.exists():
        return []
    artifacts = []
    for f in sorted(run_dir.rglob("*")):
        if f.is_file():
            rel = f.relative_to(run_dir)
            size = f.stat().st_size
            if size > 1024 * 1024:
                size_str = f"{size / (1024*1024):.1f} MB"
            elif size > 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} B"
            artifacts.append({"name": str(rel), "size": size_str})
    return artifacts


def _run_via_orchestrator(run_id: str, pdf_path: str, output_dir: str):
    """Upload PDF to MinIO, trigger SonataFlow, poll until complete."""
    import time
    from cpg_contracts.artifact_store import get_artifact_store

    try:
        store = get_artifact_store()
        if not store:
            raise RuntimeError("ARTIFACT_STORE_URL not set — cannot upload PDF")

        pdf_name = Path(pdf_path).name
        with open(pdf_path, "rb") as f:
            pdf_ref = store.put_raw(
                f"runs/{run_id}/{pdf_name}", f.read(), "application/pdf"
            )
        logger.info("Uploaded PDF to artifact store: %s", pdf_ref)

        r = http_requests.post(
            ORCHESTRATOR_URL,
            json={"pdf_ref": pdf_ref},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Orchestrator returned {r.status_code}: {r.text}")

        workflow = r.json()
        instance_id = workflow["id"]
        status_url = f"{ORCHESTRATOR_URL}/{instance_id}"
        logger.info("Workflow started: %s", instance_id)
        _active_runs[run_id] = {"status": "running", "workflow_id": instance_id}

        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            time.sleep(5)
            try:
                sr = http_requests.get(status_url, timeout=10)
                if sr.status_code == 404:
                    wf_data = workflow.get("workflowdata", {})
                    if wf_data.get("status") == "accepted":
                        continue
                    break
                wf_data = sr.json().get("workflowdata", {})
                if wf_data.get("status") == "completed":
                    break
            except http_requests.RequestException:
                continue

        from cpg_ingester.output import write_artifact
        assembly_ref = None
        if isinstance(wf_data, dict):
            ar = wf_data.get("assemblyResult", {})
            assembly_ref = ar.get("assembly_result_ref") if isinstance(ar, dict) else None

        summary = {
            "run_id": run_id,
            "pdf_path": pdf_path,
            "workflow_id": instance_id,
            "manifest_items": 0,
            "dmn_results": 0,
            "recommendations": 0,
            "escalated_items": 0,
        }

        if assembly_ref and store:
            try:
                assembly = store.get(assembly_ref)
                summary["dmn_results"] = len(assembly.get("dmn_results", []))
                summary["recommendations"] = len(assembly.get("recommendation_results", []))
                summary["manifest_items"] = len(assembly.get("item_manifest", []))
            except Exception as e:
                logger.warning("Could not fetch assembly result: %s", e)

        write_artifact(output_dir, "run-summary.json", summary)
        _active_runs[run_id] = {"status": "complete"}
        logger.info("Orchestrated run %s complete (workflow %s)", run_id, instance_id)

    except Exception as e:
        logger.error("Orchestrated run %s failed: %s", run_id, e)
        _active_runs[run_id] = {"status": "failed", "error": str(e)}


def _run_local(run_id: str, pdf_path: str, output_dir: str):
    """Run the pipeline locally (monolithic mode)."""
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from cpg_ingester.pipeline import build_pipeline

        import mlflow
        try:
            mlflow.langchain.autolog()
        except Exception:
            pass

        graph = build_pipeline()
        checkpointer = MemorySaver()
        compiled = graph.compile(checkpointer=checkpointer)

        state = {
            "run_id": run_id,
            "output_dir": output_dir,
            "pdf_path": pdf_path,
            "acp_writer_url": os.environ.get("ACP_WRITER_URL", ""),
            "litellm_url": os.environ.get("LITELLM_URL", "http://localhost:4000"),
            "llm_model": os.environ.get("LLM_MODEL", "default"),
            "llm_api_key": os.environ.get("LITELLM_API_KEY", "sk-change-me"),
        }
        config = {"configurable": {"thread_id": run_id}}

        from cpg_ingester.output import write_artifact
        result = compiled.invoke(state, config=config)

        write_artifact(output_dir, "run-summary.json", {
            "run_id": run_id,
            "pdf_path": pdf_path,
            "manifest_items": len(result.get("item_manifest", [])),
            "dmn_results": len(result.get("dmn_results", [])),
            "recommendations": len(result.get("recommendation_results", [])),
            "escalated_items": len(result.get("escalated_items", [])),
        })

        _active_runs[run_id] = {"status": "complete"}
        logger.info("Pipeline run %s complete", run_id)

    except Exception as e:
        logger.error("Pipeline run %s failed: %s", run_id, e)
        _active_runs[run_id] = {"status": "failed", "error": str(e)}


@app.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    runs = _get_runs()[:5]
    return templates.TemplateResponse(request, "upload.html", context={"runs": runs})


@app.post("/upload")
async def upload_cpg(pdf: UploadFile = File(...)):
    run_id = str(uuid.uuid4())[:8]
    output_dir = OUTPUT_BASE / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = output_dir / pdf.filename
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(pdf.file, f)

    _active_runs[run_id] = {"status": "running"}

    from threading import Thread
    split_pod_mode = ORCHESTRATOR_URL and os.environ.get("ARTIFACT_STORE_URL")
    if split_pod_mode:
        target = _run_via_orchestrator
    else:
        target = _run_local
    thread = Thread(target=target, args=(run_id, str(pdf_path), str(output_dir)), daemon=True)
    thread.start()

    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


@app.get("/runs", response_class=HTMLResponse)
async def runs_page(request: Request):
    runs = _get_runs()
    return templates.TemplateResponse(request, "runs.html", context={"runs": runs})


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail_page(request: Request, run_id: str):
    run_dir = OUTPUT_BASE / run_id

    summary = _load_json_artifact(run_dir, "run-summary.json")
    metadata = _load_json_artifact(run_dir, "metadata.json")
    section_map = _load_json_artifact(run_dir, "section-map.json")
    manifest = _load_json_artifact(run_dir, "manifest.json") or []
    escalated = _load_json_artifact(run_dir, "escalated-items.json")
    assembly_report = _load_json_artifact(run_dir, "assembly-report.json")
    artifacts = _list_artifacts(run_dir)

    decisions = [i for i in manifest if i.get("type") == "decision"]
    recommendations = [i for i in manifest if i.get("type") == "recommendation"]

    active = _active_runs.get(run_id, {})

    return templates.TemplateResponse(request, "run_detail.html", context={
        "run_id": run_id,
        "summary": summary,
        "metadata": metadata,
        "section_map": section_map,
        "manifest": manifest,
        "decisions": decisions,
        "recommendations": recommendations,
        "escalated": escalated,
        "assembly_report": assembly_report,
        "artifacts": artifacts,
        "active_status": active.get("status"),
    })


@app.get("/runs/{run_id}/artifact/{path:path}")
async def serve_artifact(run_id: str, path: str):
    file_path = OUTPUT_BASE / run_id / path
    if not file_path.exists() or not file_path.is_file():
        return HTMLResponse("<h1>Not Found</h1>", status_code=404)
    return FileResponse(file_path)


@click.command()
@click.option("--host", default="0.0.0.0")
@click.option("--port", type=int, default=8090)
def main(host: str, port: int):
    """Run the cpg-ingester web UI."""
    logging.basicConfig(level=logging.INFO)
    click.echo(f"CPG Ingester UI: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
