"""FastAPI REST API for the acp-writer service."""

import logging
import os

import requests
from fastapi import FastAPI, HTTPException, Request, Response

from acp_writer.careplan import build_careplan, extract_patient_data, invoke_decisions

logger = logging.getLogger(__name__)

KOGITO_URL = os.environ.get("KOGITO_URL", "http://localhost:8081")

app = FastAPI(
    title="ACP Writer API",
    version="0.1.0",
    description="Composes patient-specific, FHIR-compliant care plans.",
)


# --- Health ---


@app.get("/health")
def health():
    return {"status": "UP"}


@app.get("/health/ready")
def readiness():
    try:
        r = requests.get(f"{KOGITO_URL}/q/health/ready", timeout=5)
        if r.status_code == 200:
            return {"status": "UP"}
    except requests.ConnectionError:
        pass
    raise HTTPException(status_code=503, detail="Decision engine not available")


@app.get("/api/v1/status")
def status():
    kogito_status = "unavailable"
    models_deployed = 0
    try:
        r = requests.get(f"{KOGITO_URL}/q/health/ready", timeout=5)
        if r.status_code == 200:
            kogito_status = "healthy"
            models_deployed = 2
    except requests.ConnectionError:
        pass

    return {
        "version": "0.1.0",
        "decision_engine": {
            "status": kogito_status,
            "models_deployed": models_deployed,
        },
        "knowledge_base": {
            "status": "unavailable",
            "documents_ingested": 0,
        },
    }


# --- Care Plans ---


@app.post("/api/v1/careplans", status_code=201)
async def generate_careplan(request: Request):
    bundle = await request.json()

    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(status_code=400, detail="Request body must be a FHIR Bundle")

    try:
        patient_data = extract_patient_data(bundle)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        decisions = invoke_decisions(KOGITO_URL, patient_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Decision evaluation failed: {e}")

    careplan_bundle = build_careplan(patient_data["patient_id"], decisions)
    return Response(
        content=__import__("json").dumps(careplan_bundle),
        media_type="application/fhir+json",
        status_code=201,
    )


# --- Decision Models ---


@app.get("/api/v1/decisions/models")
def list_decision_models():
    return [
        {
            "id": "treatment-recommendation",
            "name": "Treatment Recommendation",
            "inputs": [
                {"name": "Systolic BP", "type": "number"},
                {"name": "Has Diabetes", "type": "boolean"},
                {"name": "Has Kidney Disease", "type": "boolean"},
            ],
            "outputs": [
                {"name": "Action", "type": "string"},
                {"name": "Medication", "type": "string"},
                {"name": "Dose", "type": "string"},
                {"name": "Follow Up Weeks", "type": "number"},
            ],
        },
        {
            "id": "monitoring-plan",
            "name": "Monitoring Plan",
            "inputs": [
                {"name": "Treatment Action", "type": "string"},
                {"name": "Has Kidney Disease", "type": "boolean"},
            ],
            "outputs": [
                {"name": "Lab Order", "type": "string"},
                {"name": "Lab Timing Weeks", "type": "number"},
            ],
        },
    ]


@app.post("/api/v1/decisions/models", status_code=501)
def deploy_decision_model():
    raise HTTPException(
        status_code=501,
        detail="Dynamic DMN deployment not implemented. Models are currently baked into the Kogito container.",
    )


@app.post("/api/v1/decisions/evaluate/{model_id}")
async def evaluate_decision(model_id: str, request: Request):
    model_map = {
        "treatment-recommendation": "Treatment%20Recommendation",
        "monitoring-plan": "Monitoring%20Plan",
    }
    kogito_path = model_map.get(model_id)
    if not kogito_path:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")

    inputs = await request.json()
    try:
        r = requests.post(f"{KOGITO_URL}/{kogito_path}", json=inputs, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decision evaluation failed: {e}")


@app.delete("/api/v1/decisions/models/{model_id}", status_code=501)
def remove_decision_model(model_id: str):
    raise HTTPException(status_code=501, detail="Not implemented")


# --- Knowledge (stubs) ---


@app.post("/api/v1/knowledge/documents", status_code=501)
def ingest_document():
    raise HTTPException(status_code=501, detail="Knowledge base not implemented. Vector store is a Phase 2 feature.")


@app.get("/api/v1/knowledge/documents", status_code=501)
def list_documents():
    raise HTTPException(status_code=501, detail="Knowledge base not implemented")


@app.post("/api/v1/knowledge/search", status_code=501)
def search_knowledge():
    raise HTTPException(status_code=501, detail="Knowledge base not implemented")
