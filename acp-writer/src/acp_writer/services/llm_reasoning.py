"""LLM Reasoning pod service — Guideline Resolver, Recommendation Retriever,
Plan Composer with Brief Reviewer loop, FHIR Semantic Reviewer.

Also handles CPG artifact management (guidelines, recommendations) since
the vector store and guidelines registry live in this pod's process.

Security profile: LLM inference + vector store, no FHIR server access.
"""

import asyncio
import logging
import os
from uuid import uuid4

import requests as http_requests
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from cpg_contracts import (
    CPGMetadata,
    Recommendation,
    RecommendationBundle,
    RecommendationSearchRequest,
    get_artifact_store,
    get_phi_store,
    post_callback,
    resolve_ref,
    store_artifact,
)
from acp_writer.api import _guidelines_store, _vector_store
from acp_writer.nodes.guideline_resolver import guideline_resolver
from acp_writer.nodes.recommendation_retriever import recommendation_retriever
from acp_writer.nodes.plan_composer import plan_composer
from acp_writer.nodes.brief_reviewer import brief_reviewer
from acp_writer.nodes.conflict_analyst import conflict_analyst
from acp_writer.nodes.fhir_semantic_reviewer import fhir_semantic_reviewer
from acp_writer.pipeline import MAX_BRIEF_REVIEWS
from acp_writer.planning_brief import render_conflicts_feedback

logger = logging.getLogger(__name__)

app = FastAPI(title="acp-writer-llm-reasoning", version="0.1.0")
_store = get_artifact_store()
_phi_store = get_phi_store()

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LLM_MODEL = os.environ.get("LLM_MODEL", "default")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "sk-change-me")


@app.get("/health")
def health():
    return {"status": "UP", "service": "llm-reasoning"}


DECISION_ENGINE_URL = os.environ.get("DECISION_ENGINE_URL", "http://acp-decision-engine:8080")


@app.get("/api/v1/status")
def status():
    de_status = "unavailable"
    models_deployed = 0
    try:
        resp = http_requests.get(f"{DECISION_ENGINE_URL}/api/v1/decisions/models", timeout=5)
        if resp.status_code == 200:
            models_deployed = len(resp.json())
            de_status = "healthy"
    except Exception:
        pass
    return {
        "decision_engine": {
            "status": de_status,
            "models_deployed": models_deployed,
        },
        "knowledge_base": {
            "status": "healthy" if _guidelines_store.count() > 0 else "empty",
            "guidelines_registered": _guidelines_store.count(),
            "recommendations_ingested": _vector_store.count(),
        },
    }


# --- CPG artifact management (used by cpg-ingester Delivery) ---


@app.post("/api/v1/guidelines", status_code=201)
async def register_guideline(request: Request):
    data = await request.json()
    metadata = CPGMetadata.model_validate(data)
    result = _guidelines_store.register(metadata)
    return result.model_dump(mode="json")


@app.post("/api/v1/knowledge/recommendations/batch", status_code=201)
async def ingest_recommendation_batch(request: Request):
    data = await request.json()
    bundle = RecommendationBundle.model_validate(data)
    _vector_store.add_batch(bundle.recommendations)
    return {
        "source_cpg": bundle.source_cpg,
        "count": len(bundle.recommendations),
        "status": "ingested",
    }


@app.post("/api/v1/knowledge/search")
async def search_knowledge(request: Request):
    data = await request.json()
    search_req = RecommendationSearchRequest.model_validate(data)
    result = _vector_store.search(search_req)
    return result.model_dump(mode="json")


# --- DMN execution (resolution + evaluation loop) ---


@app.post("/api/v1/execute-dmn")
async def execute_dmn(request: Request):
    """Execute DMN models with concept-resolution pipeline.

    Resolves DMN inputs using the concept pipeline (cache → terminology
    → display text → LLM inventory match), then evaluates each model
    via the decision-engine service. Chained models' outputs feed
    later models' inputs.
    """
    data = await request.json()
    ips_bundle = resolve_ref(data, "ips_bundle", _phi_store)
    state = {
        "ips_bundle": ips_bundle,
        "applicable_dmn_models": data.get("applicable_dmn_models", []),
        "dmn_dependency_graph": data.get("dmn_dependency_graph", []),
        "litellm_url": LITELLM_URL,
        "llm_model": LLM_MODEL,
        "llm_api_key": LLM_API_KEY,
    }

    import os
    decision_url = os.environ.get("DECISION_ENGINE_URL", "http://acp-decision-engine:8080")
    state["decision_engine_url"] = decision_url

    from acp_writer.nodes.dmn_executor import dmn_executor
    result = dmn_executor(state)
    return {"dmn_results": result.get("dmn_results", [])}


@app.post("/api/v1/execute-dmn-async")
async def execute_dmn_async(request: Request, background_tasks: BackgroundTasks):
    """Async version: accept immediately, run DMN execution in background, POST callback."""
    data = await request.json()
    callback_url = data.pop("callback_url", "")
    process_instance_id = data.pop("process_instance_id", "")
    background_tasks.add_task(_run_execute_dmn_background, data, callback_url, process_instance_id)
    return {"status": "accepted"}


def _run_execute_dmn_background(data: dict, callback_url: str, process_instance_id: str):
    try:
        ips_bundle = resolve_ref(data, "ips_bundle", _phi_store)
        state = {
            "ips_bundle": ips_bundle,
            "applicable_dmn_models": data.get("applicable_dmn_models", []),
            "dmn_dependency_graph": data.get("dmn_dependency_graph", []),
            "litellm_url": LITELLM_URL,
            "llm_model": LLM_MODEL,
            "llm_api_key": LLM_API_KEY,
        }

        import os
        decision_url = os.environ.get("DECISION_ENGINE_URL", "http://acp-decision-engine:8080")
        state["decision_engine_url"] = decision_url

        from acp_writer.nodes.dmn_executor import dmn_executor
        result = dmn_executor(state)
        result = {"dmn_results": result.get("dmn_results", [])}
    except Exception as e:
        logger.error("Execute-DMN background task failed: %s", e)
        result = {"error": str(e), "dmn_results": []}

    post_callback(callback_url, process_instance_id, "execute-dmn-done", result)


# --- Pipeline execution endpoints ---


@app.post("/api/v1/resolve")
async def resolve(request: Request):
    """Resolve applicable guidelines for patient conditions."""
    data = await request.json()
    state = {
        "condition_codes": data.get("condition_codes", []),
        "litellm_url": LITELLM_URL,
        "llm_model": LLM_MODEL,
        "llm_api_key": LLM_API_KEY,
    }
    result = guideline_resolver(state)
    return {
        "applicable_cpgs": result.get("applicable_cpgs", []),
        "applicable_dmn_models": result.get("applicable_dmn_models", []),
        "dmn_dependency_graph": result.get("dmn_dependency_graph", []),
    }


@app.post("/api/v1/resolve-async")
async def resolve_async(request: Request, background_tasks: BackgroundTasks):
    """Async version: accept immediately, run resolve in background, POST callback."""
    data = await request.json()
    callback_url = data.pop("callback_url", "")
    process_instance_id = data.pop("process_instance_id", "")
    background_tasks.add_task(_run_resolve_background, data, callback_url, process_instance_id)
    return {"status": "accepted"}


def _run_resolve_background(data: dict, callback_url: str, process_instance_id: str):
    try:
        state = {
            "condition_codes": data.get("condition_codes", []),
            "litellm_url": LITELLM_URL,
            "llm_model": LLM_MODEL,
            "llm_api_key": LLM_API_KEY,
        }
        result = guideline_resolver(state)
        result = {
            "applicable_cpgs": result.get("applicable_cpgs", []),
            "applicable_dmn_models": result.get("applicable_dmn_models", []),
            "dmn_dependency_graph": result.get("dmn_dependency_graph", []),
        }
    except Exception as e:
        logger.error("Resolve background task failed: %s", e)
        result = {"error": str(e)}

    post_callback(callback_url, process_instance_id, "resolve-done", result)


@app.post("/api/v1/retrieve")
async def retrieve(request: Request):
    """Retrieve recommendations from vector store."""
    data = await request.json()
    state = {
        "condition_codes": data.get("condition_codes", []),
        "dmn_results": data.get("dmn_results", []),
        "applicable_cpgs": data.get("applicable_cpgs", []),
    }
    result = recommendation_retriever(state)
    recs = result.get("recommendations", [])

    _, ref = store_artifact(_store, f"{uuid4()}/recommendations.json", recs)
    if ref:
        return {"recommendations_ref": ref}
    return {"recommendations": recs}


@app.post("/api/v1/retrieve-async")
async def retrieve_async(request: Request, background_tasks: BackgroundTasks):
    """Async version: accept immediately, run retrieve in background, POST callback."""
    data = await request.json()
    callback_url = data.pop("callback_url", "")
    process_instance_id = data.pop("process_instance_id", "")
    background_tasks.add_task(_run_retrieve_background, data, callback_url, process_instance_id)
    return {"status": "accepted"}


def _run_retrieve_background(data: dict, callback_url: str, process_instance_id: str):
    try:
        state = {
            "condition_codes": data.get("condition_codes", []),
            "dmn_results": data.get("dmn_results", []),
            "applicable_cpgs": data.get("applicable_cpgs", []),
        }
        result = recommendation_retriever(state)
        recs = result.get("recommendations", [])

        _, ref = store_artifact(_store, f"{uuid4()}/recommendations.json", recs)
        if ref:
            result = {"recommendations_ref": ref}
        else:
            result = {"recommendations": recs}
    except Exception as e:
        logger.error("Retrieve background task failed: %s", e)
        result = {"error": str(e)}

    post_callback(callback_url, process_instance_id, "retrieve-done", result)


def _seed_feedback(careplan_feedback: str, prior_conflicts: list | None = None) -> str:
    """Turn clinician care-plan review feedback into initial composer feedback.

    When a clinician requests changes, the workflow re-enters ComposePlan with
    their comment in ``careplan_feedback`` and a ref to the prior brief. Seeding
    the comment as the composer's initial ``brief_review_feedback`` makes
    ``plan_composer`` address it on the first pass (it renders under "Reviewer
    Feedback (address these issues)"), so the regenerated planning brief actually
    reflects the requested changes.

    ``prior_conflicts`` (the previous brief's conflicts, issue #169 F16a) are
    rendered into a "## Previously identified conflicts" block appended after the
    comment, giving the composer a referent for feedback like "resolve all
    identified conflicts as you suggested" — otherwise the comment names conflicts
    the composer can't see. Returns "" on the initial run (no comment, no prior
    conflicts) — normal composition, no seeded feedback.
    """
    careplan_feedback = (careplan_feedback or "").strip()
    conflict_block = render_conflicts_feedback(prior_conflicts or [])
    if not careplan_feedback and not conflict_block:
        return ""
    parts: list[str] = []
    if careplan_feedback:
        parts.append(
            "A clinician reviewed the previous care plan and requested the "
            f"following changes. Revise the plan to address them:\n{careplan_feedback}"
        )
    if conflict_block:
        parts.append(conflict_block)
    return "\n\n".join(parts)


def _prior_brief(data: dict) -> dict:
    """Resolve the prior planning brief for a request-changes loop (F16a/F17a).

    ``prior_brief_ref`` is empty ("") on the first pass — guard for that before
    touching the store. The stored artifact IS the planning brief dict; its
    goals/activities are the composer's revision base (F17a) and its conflicts
    seed the reviewer-feedback block + analyst continuity (F16a/F17c). Returns
    ``{}`` when there is no prior brief (first pass) so callers stay in authoring
    mode.
    """
    if not data.get("prior_brief_ref"):
        return {}
    prior_brief = resolve_ref(data, "prior_brief", _phi_store)
    return prior_brief if isinstance(prior_brief, dict) else {}


def _prompt_artifact(state: dict) -> dict:
    """Capture rendered prompts from composer state for AI-InputPrompt DocRefs.

    The monolith keeps ``plan_composer_prompt``/``conflict_prompt`` in state so
    ``fhir_bundle_generator`` can emit AI-InputPrompt DocumentReferences. The
    split path must ferry them across the compose→generate-bundle service
    boundary or the deployed bundle silently loses that prompt traceability
    (issue #169 F2). Rendered prompts embed patient data, so they go to the PHI
    store. Returns ``{}`` when no prompts were captured (e.g. capture disabled).
    """
    prompts = {
        k: state[k]
        for k in ("plan_composer_prompt", "conflict_prompt")
        if state.get(k)
    }
    if not prompts:
        return {}
    _, ref = store_artifact(_phi_store, f"{uuid4()}/prompts.json", prompts)
    return {"prompts_ref": ref} if ref else {"prompts": prompts}


def _compose_pipeline(data: dict) -> dict:
    """Synchronous compose pipeline: build state, run the brief-review loop, then
    the conflict analyst. Each stage makes a blocking LLM call, so the async
    ``/compose`` handler runs this in a worker thread (C9) to avoid stalling the
    event loop for the duration of the whole reasoning pipeline."""
    recommendations = resolve_ref(data, "recommendations", _store)
    prior_brief = _prior_brief(data)
    state = {
        "patient_reference": data.get("patient_reference", ""),
        "patient_demographics": data.get("patient_demographics", {}),
        "condition_codes": data.get("condition_codes", []),
        "medication_codes": data.get("medication_codes", []),
        "allergy_codes": data.get("allergy_codes", []),
        "dmn_results": data.get("dmn_results", []),
        "recommendations": recommendations if isinstance(recommendations, list) else [],
        "applicable_cpgs": data.get("applicable_cpgs", []),
        "litellm_url": LITELLM_URL,
        "llm_model": LLM_MODEL,
        "llm_api_key": LLM_API_KEY,
        "brief_review_count": 0,
        # Prior brief drives plan_composer revision mode + analyst continuity
        # (F17a/F17c); its conflicts also seed the reviewer-feedback block (F16a).
        "prior_planning_brief": prior_brief,
        "careplan_review_history": data.get("careplan_review_history", []),
        # Raw latest clinician instruction — the analyst reads it on a revision
        # pass to record which conflicts the clinician directed resolved (F17c).
        "careplan_feedback": data.get("careplan_feedback", ""),
        "brief_review_feedback": _seed_feedback(
            data.get("careplan_feedback", ""), prior_brief.get("conflicts") or []
        ),
    }

    for _ in range(MAX_BRIEF_REVIEWS + 1):
        updates = plan_composer(state)
        state.update(updates)

        updates = brief_reviewer(state)
        state.update(updates)

        if not state.get("brief_review_feedback"):
            break
        if state.get("brief_review_count", 0) >= MAX_BRIEF_REVIEWS:
            break

    # Detect plan-level conflicts on the converged brief (annotates the brief in
    # place — never edits goals/activities). Mirrors the monolith pipeline order
    # (brief-review loop → conflict_analyst → FHIR generation) so the split /
    # SonataFlow path surfaces conflicts too; the brief carries them downstream
    # to fhir_bundle_generator, which emits the conflict Provenances.
    state.update(conflict_analyst(state))

    brief = state.get("planning_brief", {})
    result = _prompt_artifact(state)
    _, ref = store_artifact(_phi_store, f"{uuid4()}/planning_brief.json", brief)
    if ref:
        result["planning_brief_ref"] = ref
    else:
        result["planning_brief"] = brief
    return result


@app.post("/api/v1/compose")
async def compose(request: Request):
    """Run Plan Composer with Brief Reviewer loop."""
    data = await request.json()
    return await asyncio.to_thread(_compose_pipeline, data)


@app.post("/api/v1/compose-async")
async def compose_async(request: Request, background_tasks: BackgroundTasks):
    """Async version: accept immediately, run compose in background, POST callback."""
    data = await request.json()
    callback_url = data.pop("callback_url", "")
    process_instance_id = data.pop("process_instance_id", "")
    background_tasks.add_task(_run_compose_background, data, callback_url, process_instance_id)
    return {"status": "accepted"}


def _run_compose_background(data: dict, callback_url: str, process_instance_id: str):
    try:
        recommendations = resolve_ref(data, "recommendations", _store)
        prior_brief = _prior_brief(data)
        state = {
            "patient_reference": data.get("patient_reference", ""),
            "patient_demographics": data.get("patient_demographics", {}),
            "condition_codes": data.get("condition_codes", []),
            "medication_codes": data.get("medication_codes", []),
            "allergy_codes": data.get("allergy_codes", []),
            "dmn_results": data.get("dmn_results", []),
            "recommendations": recommendations if isinstance(recommendations, list) else [],
            "applicable_cpgs": data.get("applicable_cpgs", []),
            "litellm_url": LITELLM_URL,
            "llm_model": LLM_MODEL,
            "llm_api_key": LLM_API_KEY,
            "brief_review_count": 0,
            # Prior brief drives plan_composer revision mode + analyst continuity
            # (F17a/F17c); its conflicts also seed the reviewer-feedback block (F16a).
            "prior_planning_brief": prior_brief,
            "careplan_review_history": data.get("careplan_review_history", []),
            # Raw latest clinician instruction — the analyst reads it on a revision
            # pass to record which conflicts the clinician directed resolved (F17c).
            "careplan_feedback": data.get("careplan_feedback", ""),
            "brief_review_feedback": _seed_feedback(
                data.get("careplan_feedback", ""), prior_brief.get("conflicts") or []
            ),
        }

        for _ in range(MAX_BRIEF_REVIEWS + 1):
            updates = plan_composer(state)
            state.update(updates)
            updates = brief_reviewer(state)
            state.update(updates)
            if not state.get("brief_review_feedback"):
                break
            if state.get("brief_review_count", 0) >= MAX_BRIEF_REVIEWS:
                break

        # Detect plan-level conflicts on the converged brief (see the sync
        # /compose handler). The brief carries the conflicts downstream to
        # fhir_bundle_generator, which emits the conflict Provenances.
        state.update(conflict_analyst(state))

        brief = state.get("planning_brief", {})
        result = _prompt_artifact(state)
        _, ref = store_artifact(_phi_store, f"{uuid4()}/planning_brief.json", brief)
        if ref:
            result["planning_brief_ref"] = ref
        elif _phi_store:
            raise RuntimeError("Artifact store available but failed to store planning brief")
        else:
            result["planning_brief"] = brief
    except Exception as e:
        logger.error("Compose background task failed: %s", e)
        result = {"error": str(e)}

    post_callback(callback_url, process_instance_id, "compose-done", result)


@app.post("/api/v1/review-fhir")
async def review_fhir(request: Request):
    """Run FHIR Semantic Reviewer."""
    data = await request.json()
    fhir_bundle = resolve_ref(data, "fhir_bundle", _phi_store)
    state = {
        "fhir_bundle": fhir_bundle,
        "terminology_issues": data.get("terminology_issues", []),
        "syntax_errors": data.get("syntax_errors", []),
        "fhir_review_count": data.get("fhir_review_count", 0),
        "litellm_url": LITELLM_URL,
        "llm_model": LLM_MODEL,
        "llm_api_key": LLM_API_KEY,
    }
    result = fhir_semantic_reviewer(state)
    return {
        "fhir_review_feedback": result.get("fhir_review_feedback", ""),
        "fhir_review_count": result.get("fhir_review_count", 0),
    }


@app.post("/api/v1/review-fhir-async")
async def review_fhir_async(request: Request, background_tasks: BackgroundTasks):
    """Async version: accept immediately, run review in background, POST callback."""
    data = await request.json()
    callback_url = data.pop("callback_url", "")
    process_instance_id = data.pop("process_instance_id", "")
    background_tasks.add_task(_run_review_fhir_background, data, callback_url, process_instance_id)
    return {"status": "accepted"}


def _run_review_fhir_background(data: dict, callback_url: str, process_instance_id: str):
    try:
        fhir_bundle = resolve_ref(data, "fhir_bundle", _phi_store)
        state = {
            "fhir_bundle": fhir_bundle,
            "terminology_issues": data.get("terminology_issues", []),
            "syntax_errors": data.get("syntax_errors", []),
            "fhir_review_count": data.get("fhir_review_count", 0),
            "litellm_url": LITELLM_URL,
            "llm_model": LLM_MODEL,
            "llm_api_key": LLM_API_KEY,
        }
        result_state = fhir_semantic_reviewer(state)
        result = {
            "fhir_review_feedback": result_state.get("fhir_review_feedback", ""),
            "fhir_review_count": result_state.get("fhir_review_count", 0),
        }
    except Exception as e:
        logger.error("Review-FHIR background task failed: %s", e)
        result = {"error": str(e), "fhir_review_feedback": "", "fhir_review_count": 0}

    post_callback(callback_url, process_instance_id, "review-done", result)
