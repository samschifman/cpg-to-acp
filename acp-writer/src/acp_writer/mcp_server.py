"""MCP server exposing acp-writer tools via the Model Context Protocol."""

import json
import os

import mlflow
from mcp.server.fastmcp import FastMCP

from acp_writer.careplan import build_careplan, extract_patient_data
from acp_writer.api import _dynamic_models, _evaluate_jit, _parse_dmn_metadata

mcp = FastMCP("acp-writer")

KOGITO_URL = os.environ.get("KOGITO_URL", "http://localhost:8081")


@mcp.tool()
@mlflow.trace(name="mcp_deploy_decision_model")
def deploy_decision_model(dmn_xml: str) -> str:
    """Deploy a DMN decision model to the care plan writer's internal decision engine."""
    summary = _parse_dmn_metadata(dmn_xml)
    _dynamic_models[summary.id] = {"summary": summary, "dmn_xml": dmn_xml}
    return json.dumps(summary.model_dump(mode="json"))


@mcp.tool()
@mlflow.trace(name="mcp_list_decision_models")
def list_decision_models() -> str:
    """List all decision models currently deployed."""
    models = [m["summary"].model_dump(mode="json") for m in _dynamic_models.values()]
    return json.dumps(models)


@mcp.tool()
@mlflow.trace(name="mcp_evaluate_decision")
def evaluate_decision(model_id: str, inputs: dict) -> str:
    """Evaluate a deployed DMN decision model with the given inputs."""
    model = _dynamic_models.get(model_id)
    if not model:
        return json.dumps({"error": f"Model '{model_id}' not found"})
    result = _evaluate_jit(model["dmn_xml"], inputs)
    return json.dumps(result)


@mcp.tool()
@mlflow.trace(name="mcp_generate_careplan")
def generate_careplan(patient_data: dict) -> str:
    """Generate a patient-specific FHIR CarePlan from a FHIR Bundle."""
    extracted = extract_patient_data(patient_data)

    treatment_model = _dynamic_models.get("treatment-recommendation")
    monitoring_model = _dynamic_models.get("monitoring-plan")
    if not treatment_model or not monitoring_model:
        return json.dumps({"error": "Required decision models not deployed"})

    treatment_result = _evaluate_jit(
        treatment_model["dmn_xml"],
        {
            "Systolic BP": extracted["systolic_bp"],
            "Has Diabetes": extracted["has_diabetes"],
            "Has Kidney Disease": extracted["has_kidney_disease"],
        },
    )
    action = treatment_result["Treatment Recommendation"]["Action"]
    monitoring_result = _evaluate_jit(
        monitoring_model["dmn_xml"],
        {"Treatment Action": action, "Has Kidney Disease": extracted["has_kidney_disease"]},
    )

    decisions = {
        "action": action,
        "medication": treatment_result["Treatment Recommendation"]["Medication"],
        "dose": treatment_result["Treatment Recommendation"]["Dose"],
        "follow_up_weeks": treatment_result["Treatment Recommendation"]["Follow Up Weeks"],
        "lab_order": monitoring_result["Monitoring Plan"]["Lab Order"],
        "lab_timing_weeks": monitoring_result["Monitoring Plan"]["Lab Timing Weeks"],
    }

    bundle = build_careplan(extracted["patient_id"], decisions)
    return json.dumps(bundle)
