"""Compose a FHIR CarePlan from patient data and DMN decision outputs.

Phase 1 shortcut: hardcoded FHIR-to-DMN mapping and direct resource queries.
These do not generalize and must be replaced in Phase 2.
"""

import json
import logging
import uuid

import click
import requests

logger = logging.getLogger(__name__)


# --- Phase 1 shortcut: hardcoded FHIR queries and DMN input mapping ---
# This knows exactly which FHIR resources to query and how to extract
# the values needed for the hypertension decision tables. It does not
# generalize to other CPGs or decision tables.


def query_patient_data(fhir_url: str, patient_id: str) -> dict:
    """Query FHIR for patient data and extract DMN inputs.

    Phase 1 shortcut: hardcoded resource queries specific to the
    hypertension decision tables. Replace with IPS in Phase 2.
    """
    patient = requests.get(f"{fhir_url}/Patient/{patient_id}").json()
    name = patient.get("name", [{}])[0]
    patient_name = f"{name.get('given', [''])[0]} {name.get('family', '')}"

    conditions = requests.get(
        f"{fhir_url}/Condition",
        params={"patient": patient_id, "_format": "json"},
    ).json()

    has_diabetes = False
    has_kidney_disease = False
    for entry in conditions.get("entry", []):
        codings = entry["resource"]["code"].get("coding", [])
        for coding in codings:
            if coding.get("code") == "44054006":
                has_diabetes = True
            if coding.get("code") == "90688005":
                has_kidney_disease = True

    observations = requests.get(
        f"{fhir_url}/Observation",
        params={"patient": patient_id, "code": "85354-9", "_format": "json"},
    ).json()

    systolic_bp = None
    for entry in observations.get("entry", []):
        for component in entry["resource"].get("component", []):
            code = component["code"]["coding"][0]["code"]
            if code == "8480-6":
                systolic_bp = component["valueQuantity"]["value"]

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
    treatment = requests.post(
        f"{kogito_url}/Treatment%20Recommendation",
        json={
            "Systolic BP": patient_data["systolic_bp"],
            "Has Diabetes": patient_data["has_diabetes"],
            "Has Kidney Disease": patient_data["has_kidney_disease"],
        },
    ).json()

    action = treatment["Treatment Recommendation"]["Action"]

    monitoring = requests.post(
        f"{kogito_url}/Monitoring%20Plan",
        json={
            "Treatment Action": action,
            "Has Kidney Disease": patient_data["has_kidney_disease"],
        },
    ).json()

    result = {
        "action": treatment["Treatment Recommendation"]["Action"],
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


@click.command()
@click.argument("patient_id")
@click.option("--fhir-url", default="http://localhost:8080/fhir", help="HAPI FHIR base URL.")
@click.option("--kogito-url", default="http://localhost:8081", help="Kogito decision service URL.")
@click.option("--output", "-o", type=click.Path(), default=None, help="Write CarePlan JSON to file.")
def main(patient_id: str, fhir_url: str, kogito_url: str, output: str):
    """Generate a FHIR CarePlan for a patient using DMN decisions."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    patient_data = query_patient_data(fhir_url, patient_id)
    decisions = invoke_decisions(kogito_url, patient_data)
    careplan_bundle = build_careplan(patient_id, decisions)

    careplan_json = json.dumps(careplan_bundle, indent=2)

    if output:
        with open(output, "w") as f:
            f.write(careplan_json)
        click.echo(f"CarePlan written to {output}")
    else:
        click.echo(careplan_json)


if __name__ == "__main__":
    main()
