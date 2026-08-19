"""Canned clinical content for the mock BFF (hypertension exemplar).

`make_patient_summary` prefers a real name from an uploaded IPS bundle but falls
back to the exemplar, so uploads feel personalized without parsing full FHIR.
"""

from __future__ import annotations

from acp_writer.services import bff_models as m

_EXEMPLAR_PATIENT = m.PatientSummary(
    name="Jordan Rivera",
    birth_date="1957-03-12",
    gender="female",
    patient_reference="Patient/example-htn",
    conditions=[
        m.CodedItem(display="Essential hypertension", code="59621000", system="http://snomed.info/sct"),
        m.CodedItem(display="Type 2 diabetes mellitus", code="44054006", system="http://snomed.info/sct"),
    ],
    medications=[
        m.CodedItem(display="Metformin 500 mg", code="860975", system="http://www.nlm.nih.gov/research/umls/rxnorm"),
    ],
    allergies=[m.CodedItem(display="No known drug allergies", code="716186003", system="http://snomed.info/sct")],
    observations=[
        m.CodedItem(display="Systolic BP 152 mmHg", code="8480-6", system="http://loinc.org"),
        m.CodedItem(display="Diastolic BP 94 mmHg", code="8462-4", system="http://loinc.org"),
    ],
)

_CARE_PLAN = m.CarePlanView(
    goals=[
        m.PlanGoal(id="goal-1", description="Reduce blood pressure to < 130/80 mmHg within 3 months",
                   rationale="Stage 2 hypertension with diabetes comorbidity", source_cpg_id="AHA-HTN-2024"),
        m.PlanGoal(id="goal-2", description="Maintain HbA1c < 7.0%",
                   rationale="Diabetes co-management supports BP control", source_cpg_id="ADA-2024"),
    ],
    activities=[
        m.PlanActivity(id="act-1", goal_id="goal-1", description="Start lisinopril 10 mg daily",
                       detail="ACE inhibitor first-line for HTN + diabetes"),
        m.PlanActivity(id="act-2", goal_id="goal-1", description="DASH diet + sodium < 1500 mg/day",
                       detail="Lifestyle modification"),
        m.PlanActivity(id="act-3", goal_id="goal-2", description="Continue metformin 500 mg BID",
                       detail="No change"),
    ],
    conflicts=[
        m.PlanConflict(id="conf-1", severity=m.Severity.warning,
                       description="Monitor potassium: ACE inhibitor with existing renal risk"),
    ],
    fhir_bundle={
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "example-htn", "name": [{"text": "Jordan Rivera"}]}},
            {"resource": {"resourceType": "CarePlan", "id": "cp-example", "status": "draft",
                          "intent": "plan", "subject": {"reference": "Patient/example-htn"},
                          "description": "Hypertension management plan"}},
            {"resource": {"resourceType": "Goal", "id": "goal-1", "lifecycleStatus": "active",
                          "description": {"text": "Reduce blood pressure to < 130/80 mmHg"}}},
        ],
    },
)


def make_patient_summary(ips_bundle: dict) -> m.PatientSummary:
    """Return the exemplar patient, overriding the name from the IPS bundle if present."""
    patient = _EXEMPLAR_PATIENT.model_copy(deep=True)
    try:
        for entry in ips_bundle.get("entry", []):
            res = entry.get("resource", {})
            if res.get("resourceType") == "Patient":
                names = res.get("name") or []
                if names:
                    n = names[0]
                    patient.name = n.get("text") or " ".join(
                        [*n.get("given", []), n.get("family", "")]
                    ).strip() or patient.name
                ref_id = res.get("id")
                if ref_id:
                    patient.patient_reference = f"Patient/{ref_id}"
                break
    except AttributeError:
        pass
    return patient


def make_care_plan_view() -> m.CarePlanView:
    return _CARE_PLAN.model_copy(deep=True)
