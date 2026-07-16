"""Core care plan composition logic.

Extracts patient data from FHIR Bundles, invokes DMN decision services,
and builds FHIR CarePlan Bundles.

Phase 1 shortcut: extract_patient_data is hardcoded to the hypertension
decision tables. It does not generalize to other CPGs.
"""

import logging
import uuid

import requests

logger = logging.getLogger(__name__)

SNOMED_DIABETES = "44054006"
SNOMED_CKD = "90688005"
LOINC_BP_PANEL = "85354-9"
LOINC_SYSTOLIC = "8480-6"


def extract_patient_data(bundle: dict) -> dict:
    """Extract DMN inputs from a FHIR Bundle.

    Phase 1 shortcut: hardcoded extraction specific to the hypertension
    decision tables. Accepts any FHIR Bundle type (transaction, collection,
    searchset) and strips request metadata.
    """
    resources = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", entry)
        if "resourceType" in resource:
            resources.append(resource)

    patient_id = None
    patient_name = ""
    has_diabetes = False
    has_kidney_disease = False
    systolic_bp = None

    for r in resources:
        rt = r.get("resourceType")

        if rt == "Patient":
            patient_id = r.get("id")
            name = r.get("name", [{}])[0]
            patient_name = f"{name.get('given', [''])[0]} {name.get('family', '')}"

        elif rt == "Condition":
            for coding in r.get("code", {}).get("coding", []):
                if coding.get("code") == SNOMED_DIABETES:
                    has_diabetes = True
                if coding.get("code") == SNOMED_CKD:
                    has_kidney_disease = True

        elif rt == "Observation":
            for coding in r.get("code", {}).get("coding", []):
                if coding.get("code") == LOINC_BP_PANEL:
                    for component in r.get("component", []):
                        comp_code = (
                            component.get("code", {})
                            .get("coding", [{}])[0]
                            .get("code")
                        )
                        if comp_code == LOINC_SYSTOLIC:
                            quantity = component.get("valueQuantity", {})
                            systolic_bp = quantity.get("value")

    if patient_id is None:
        raise ValueError("No Patient resource found in bundle")
    if systolic_bp is None:
        raise ValueError("No blood pressure Observation found in bundle")

    logger.info(
        "Patient %s (%s): systolic=%s, diabetes=%s, kidney=%s",
        patient_id, patient_name, systolic_bp, has_diabetes, has_kidney_disease,
    )

    return {
        "patient_id": patient_id,
        "patient_name": patient_name,
        "systolic_bp": systolic_bp,
        "has_diabetes": has_diabetes,
        "has_kidney_disease": has_kidney_disease,
    }


def invoke_decisions(kogito_url: str, patient_data: dict) -> dict:
    """Call Kogito DMN endpoints and return combined decision outputs."""
    session = requests.Session()

    r = session.post(
        f"{kogito_url}/Treatment%20Recommendation",
        json={
            "Systolic BP": patient_data["systolic_bp"],
            "Has Diabetes": patient_data["has_diabetes"],
            "Has Kidney Disease": patient_data["has_kidney_disease"],
        },
        timeout=10,
    )
    r.raise_for_status()
    treatment = r.json()

    action = treatment["Treatment Recommendation"]["Action"]

    r = session.post(
        f"{kogito_url}/Monitoring%20Plan",
        json={
            "Treatment Action": action,
            "Has Kidney Disease": patient_data["has_kidney_disease"],
        },
        timeout=10,
    )
    r.raise_for_status()
    monitoring = r.json()

    result = {
        "action": action,
        "medication": treatment["Treatment Recommendation"]["Medication"],
        "dose": treatment["Treatment Recommendation"]["Dose"],
        "follow_up_weeks": treatment["Treatment Recommendation"]["Follow Up Weeks"],
        "lab_order": monitoring["Monitoring Plan"]["Lab Order"],
        "lab_timing_weeks": monitoring["Monitoring Plan"]["Lab Timing Weeks"],
    }
    logger.info("Decision outputs: %s", result)
    return result


def build_careplan(patient_id: str, decisions: dict) -> dict:
    """Build a FHIR CarePlan Bundle from DMN decision outputs."""
    entries = []

    goal_id = str(uuid.uuid4())
    goal = {
        "resourceType": "Goal",
        "id": goal_id,
        "lifecycleStatus": "proposed",
        "description": {
            "text": "Lower blood pressure to target range",
        },
        "subject": {"reference": f"Patient/{patient_id}"},
    }
    entries.append(goal)

    activities = []

    if decisions["action"] == "Start medication" and decisions["medication"] != "-":
        med_req_id = str(uuid.uuid4())
        med_request = {
            "resourceType": "MedicationRequest",
            "id": med_req_id,
            "status": "draft",
            "intent": "proposal",
            "medicationCodeableConcept": {
                "text": f"{decisions['medication']} {decisions['dose']}",
            },
            "subject": {"reference": f"Patient/{patient_id}"},
        }
        entries.append(med_request)
        activities.append({
            "reference": {"reference": f"MedicationRequest/{med_req_id}"},
        })

    if decisions["follow_up_weeks"] and decisions["follow_up_weeks"] > 0:
        followup_id = str(uuid.uuid4())
        followup = {
            "resourceType": "ServiceRequest",
            "id": followup_id,
            "status": "draft",
            "intent": "proposal",
            "code": {"text": "Follow-up appointment"},
            "subject": {"reference": f"Patient/{patient_id}"},
            "occurrenceTiming": {
                "repeat": {
                    "frequency": 1,
                    "period": decisions["follow_up_weeks"],
                    "periodUnit": "wk",
                },
            },
        }
        entries.append(followup)
        activities.append({
            "reference": {"reference": f"ServiceRequest/{followup_id}"},
        })

    if decisions["lab_order"] and decisions["lab_order"] != "-":
        lab_id = str(uuid.uuid4())
        lab_request = {
            "resourceType": "ServiceRequest",
            "id": lab_id,
            "status": "draft",
            "intent": "proposal",
            "code": {"text": decisions["lab_order"]},
            "subject": {"reference": f"Patient/{patient_id}"},
            "occurrenceTiming": {
                "repeat": {
                    "frequency": 1,
                    "period": decisions["lab_timing_weeks"],
                    "periodUnit": "wk",
                },
            },
        }
        entries.append(lab_request)
        activities.append({
            "reference": {"reference": f"ServiceRequest/{lab_id}"},
        })

    careplan_id = str(uuid.uuid4())
    careplan = {
        "resourceType": "CarePlan",
        "id": careplan_id,
        "status": "draft",
        "intent": "proposal",
        "title": "Hypertension Management Plan",
        "subject": {"reference": f"Patient/{patient_id}"},
        "goal": [{"reference": f"Goal/{goal_id}"}],
        "activity": activities,
    }
    entries.append(careplan)

    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": r} for r in entries],
    }
    return bundle
