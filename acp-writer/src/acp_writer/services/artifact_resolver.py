"""Resolve artifact refs in run details by fetching data from MinIO.

The sonataflow_client produces a RunDetail with raw ``workflowData``;
this module hydrates ref keys into the fields the UI expects.
PHI data (IPS bundles, planning briefs, FHIR bundles) lives in the
cpg-phi bucket; non-PHI data (recommendations) in cpg-artifacts.
"""

import logging
from typing import Any

from cpg_contracts.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)


def _fetch_ref(store: ArtifactStore, ref: str) -> dict | None:
    try:
        return store.get(ref)
    except Exception as exc:
        logger.warning("Could not resolve artifact ref %s: %s", ref, exc)
        return None


def _to_coded_items(codes: list | None) -> list[dict]:
    """Convert internal code lists to the contract's CodedItem[] shape."""
    if not codes:
        return []
    items = []
    for c in codes:
        if isinstance(c, dict):
            items.append({
                "display": c.get("display", c.get("name", str(c.get("code", "")))),
                "code": c.get("code", ""),
                "system": c.get("system", ""),
            })
        elif isinstance(c, str):
            items.append({"display": c})
    return items


def enrich_run_detail(
    detail: dict[str, Any],
    phi_store: ArtifactStore | None,
    artifacts_store: ArtifactStore | None,
) -> dict[str, Any]:
    """Resolve artifact refs in a RunDetail and populate UI-facing fields.

    Mutates and returns ``detail``.  The ``workflowData`` key is consumed
    and removed — it is an internal transport field, not part of the API.
    """
    wd = detail.pop("workflowData", None)
    if not wd:
        return detail

    errors: list[dict[str, str]] = []
    store = phi_store or artifacts_store

    # --- Patient data → PatientSummary ---
    patient_raw = wd.get("patientData") or {}
    if patient_raw:
        demographics = patient_raw.get("patient_demographics") or {}
        detail["patient"] = {
            "name": demographics.get("name", ""),
            "birthDate": demographics.get("birth_date", ""),
            "gender": demographics.get("gender", ""),
            "patientReference": patient_raw.get("patient_reference", ""),
            "conditions": _to_coded_items(patient_raw.get("condition_codes")),
            "medications": _to_coded_items(patient_raw.get("medication_codes")),
            "allergies": _to_coded_items(patient_raw.get("allergy_codes")),
        }

    # --- Guideline data (kept for internal use, not in UI contract) ---
    guideline_raw = wd.get("guidelineData") or {}
    if guideline_raw:
        detail["applicableCpgs"] = guideline_raw.get("applicable_cpgs")
        detail["applicableDmnModels"] = guideline_raw.get("applicable_dmn_models")

    # --- DMN results ---
    dmn_raw = wd.get("dmnData") or {}
    if "error" in dmn_raw:
        errors.append({"stepKey": "execute_dmn", "message": str(dmn_raw["error"])})
    elif dmn_raw:
        detail["dmnResults"] = dmn_raw.get("dmn_results")

    # --- Recommendations ---
    rec_raw = wd.get("recData") or {}
    if "error" in rec_raw:
        errors.append({"stepKey": "retrieve_recommendations", "message": str(rec_raw["error"])})
    elif rec_raw:
        rec_data = rec_raw
        ref = rec_raw.get("recommendations_ref")
        if ref and store:
            resolved = _fetch_ref(store, ref)
            if resolved:
                rec_data = resolved
        if isinstance(rec_data, dict):
            detail["recommendations"] = rec_data.get("recommendations", rec_data)
        else:
            detail["recommendations"] = rec_data

    # --- Planning brief (from ComposePlan) → PlanningBrief ---
    composer_raw = wd.get("composerData") or {}
    planning_brief = None
    if "error" in composer_raw:
        errors.append({"stepKey": "compose_plan", "message": str(composer_raw["error"])})
    elif composer_raw:
        brief = composer_raw
        ref = composer_raw.get("planning_brief_ref")
        if ref and phi_store:
            resolved = _fetch_ref(phi_store, ref)
            if resolved:
                brief = resolved
        planning_brief = brief.get("planning_brief", brief)
        detail["planningBrief"] = planning_brief

    # --- FHIR generation → CarePlanView ---
    fhir_gen_raw = wd.get("fhirGenData") or {}
    fhir_bundle = None
    if "error" in fhir_gen_raw:
        errors.append({"stepKey": "generate_bundle", "message": str(fhir_gen_raw["error"])})
    elif fhir_gen_raw:
        bundle = fhir_gen_raw
        ref = fhir_gen_raw.get("fhir_bundle_ref")
        if ref and phi_store:
            resolved = _fetch_ref(phi_store, ref)
            if resolved:
                bundle = resolved
        fhir_bundle = bundle.get("fhir_bundle", bundle)

        care_plan_view: dict[str, Any] = {"fhirBundle": fhir_bundle}
        if planning_brief and isinstance(planning_brief, dict):
            care_plan_view["goals"] = planning_brief.get("goals", [])
            care_plan_view["activities"] = planning_brief.get("activities", [])
            care_plan_view["conflicts"] = planning_brief.get("conflicts", [])
        detail["carePlan"] = care_plan_view

    # --- FHIR review (automated) ---
    fhir_review_raw = wd.get("fhirReviewData") or {}
    if fhir_review_raw:
        detail["fhirReviewFeedback"] = fhir_review_raw.get("fhir_review_feedback")

    # --- Write result ---
    write_raw = wd.get("writeResult") or {}
    if "error" in write_raw:
        errors.append({"stepKey": "write_fhir", "message": str(write_raw["error"])})
    elif write_raw:
        detail["careplanId"] = write_raw.get("careplan_id")

    if errors:
        detail["errors"] = errors

    return detail
