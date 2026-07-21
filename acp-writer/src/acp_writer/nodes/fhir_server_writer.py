"""FHIR Server Writer — POST transaction Bundle to HAPI FHIR server.

Validates OperationOutcome response and stores care plan reference.
Supports approve/reject workflow with AI Transparency tag transitions.
"""

import json
import logging
import os
import uuid

import mlflow
import requests

from acp_writer.output import write_artifact
from acp_writer.state import CarePlanComposerState

logger = logging.getLogger(__name__)

FHIR_SERVER_URL = os.environ.get("FHIR_SERVER_URL", "http://localhost:8080/fhir")

_care_plans: dict[str, dict] = {}


@mlflow.trace(name="fhir_server_writer")
def fhir_server_writer(state: CarePlanComposerState) -> dict:
    """Write the FHIR Bundle to the HAPI FHIR server."""
    bundle = state.get("fhir_bundle", {})
    output_dir = state.get("output_dir", "")

    if not bundle.get("entry"):
        logger.info("Empty FHIR bundle — skipping server write")
        return {"delivery_status": "skipped", "careplan_id": ""}

    careplan_id = str(uuid.uuid4())

    _care_plans[careplan_id] = {
        "id": careplan_id,
        "bundle": bundle,
        "status": "draft",
        "patient_reference": state.get("patient_reference", ""),
    }

    try:
        r = requests.post(
            FHIR_SERVER_URL,
            json=bundle,
            headers={"Content-Type": "application/fhir+json"},
            timeout=30,
        )

        response_data = r.json() if r.content else {}

        if r.status_code in (200, 201):
            logger.info("FHIR Bundle posted successfully (status %d)", r.status_code)
            _care_plans[careplan_id]["fhir_response"] = response_data

            if output_dir:
                write_artifact(output_dir, "fhir-server-response.json", response_data)

            return {
                "fhir_server_response": response_data,
                "careplan_id": careplan_id,
                "delivery_status": "delivered",
            }
        else:
            logger.warning("FHIR server returned %d: %s", r.status_code, r.text[:200])
            _care_plans[careplan_id]["error"] = r.text[:500]
            return {
                "fhir_server_response": response_data,
                "careplan_id": careplan_id,
                "delivery_status": "error",
            }

    except requests.RequestException as e:
        logger.warning("FHIR server unavailable: %s — storing locally only", e)
        return {
            "fhir_server_response": {},
            "careplan_id": careplan_id,
            "delivery_status": "stored_locally",
        }


def get_care_plan(careplan_id: str) -> dict | None:
    return _care_plans.get(careplan_id)


def list_care_plans(patient: str | None = None, status: str | None = None) -> list[dict]:
    results = list(_care_plans.values())
    if patient:
        results = [cp for cp in results if cp.get("patient_reference") == patient]
    if status:
        results = [cp for cp in results if cp.get("status") == status]
    return [{
        "id": cp["id"],
        "patient_reference": cp.get("patient_reference", ""),
        "status": cp.get("status", ""),
    } for cp in results]


CLINAST_AIRPT_SECURITY = {
    "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationValue",
    "code": "CLINAST_AIRPT",
    "display": "clinician asserted from AI reported",
}


def approve_care_plan(careplan_id: str, clinician: str | None = None) -> dict | None:
    """Approve a care plan: status→active, AIAST→CLINAST_AIRPT."""
    cp = _care_plans.get(careplan_id)
    if not cp:
        return None

    cp["status"] = "active"
    bundle = cp.get("bundle", {})

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        security = resource.get("meta", {}).get("security", [])
        for i, sec in enumerate(security):
            if sec.get("code") == "AIAST":
                security[i] = CLINAST_AIRPT_SECURITY

        if resource.get("resourceType") == "CarePlan":
            resource["status"] = "active"

        if resource.get("resourceType") == "Provenance":
            profiles = resource.get("meta", {}).get("profile", [])
            if any("AI-Provenance" in p for p in profiles):
                agents = resource.get("agent", [])
                agents.append({
                    "type": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                            "code": "verifier",
                        }],
                    },
                    "who": {"display": clinician or "Clinician"},
                })

    return {"id": careplan_id, "status": "active"}


def reject_care_plan(careplan_id: str, reason: str) -> dict | None:
    """Reject a care plan: status→revoked, record reason."""
    cp = _care_plans.get(careplan_id)
    if not cp:
        return None

    cp["status"] = "revoked"
    bundle = cp.get("bundle", {})

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "CarePlan":
            resource["status"] = "revoked"
            notes = resource.get("note", [])
            notes.append({"text": f"Rejected: {reason}"})
            resource["note"] = notes

    return {"id": careplan_id, "status": "revoked", "reason": reason}
