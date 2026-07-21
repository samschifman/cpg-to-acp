"""IPS Extractor — targeted data extraction from IPS Bundle.

Used by DMN Executor for on-demand extraction of specific
observations, conditions, medications, and allergies by code.
Returns FHIR resource references for audit trail.
"""

import logging
from datetime import datetime
from typing import Any

import mlflow

logger = logging.getLogger(__name__)


class ExtractionResult:
    """Result of a targeted IPS extraction."""

    def __init__(
        self,
        found: bool,
        value: Any = None,
        unit: str | None = None,
        date: str | None = None,
        fhir_reference: str | None = None,
        resource_type: str | None = None,
    ):
        self.found = found
        self.value = value
        self.unit = unit
        self.date = date
        self.fhir_reference = fhir_reference
        self.resource_type = resource_type

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"found": self.found}
        if self.value is not None:
            d["value"] = self.value
        if self.unit:
            d["unit"] = self.unit
        if self.date:
            d["date"] = self.date
        if self.fhir_reference:
            d["fhir_reference"] = self.fhir_reference
        if self.resource_type:
            d["resource_type"] = self.resource_type
        return d


def _get_resources(bundle: dict, resource_type: str) -> list[dict]:
    return [
        e["resource"]
        for e in bundle.get("entry", [])
        if e.get("resource", {}).get("resourceType") == resource_type
    ]


def _has_code(resource: dict, code_field: str, system: str, code: str) -> bool:
    cc = resource.get(code_field, {})
    for coding in cc.get("coding", []):
        if coding.get("system") == system and coding.get("code") == code:
            return True
    return False


def _get_effective_date(resource: dict) -> str | None:
    for field in ["effectiveDateTime", "effectivePeriod", "issued"]:
        val = resource.get(field)
        if val:
            if isinstance(val, dict):
                return val.get("start") or val.get("end")
            return val
    return None


def _parse_date_key(date_str: str | None) -> str:
    """Return a sortable string for date comparison."""
    if not date_str:
        return ""
    return date_str


@mlflow.trace(name="ips_extract_observation")
def extract_observation(
    ips_bundle: dict, system: str, code: str
) -> ExtractionResult:
    """Extract the most recent observation matching a LOINC/SNOMED code.

    For panel observations (like BP), checks both top-level code and components.
    """
    observations = _get_resources(ips_bundle, "Observation")

    candidates: list[tuple[str, dict, Any, str | None]] = []

    for obs in observations:
        effective = _get_effective_date(obs)
        ref = f"Observation/{obs.get('id', 'unknown')}"

        if _has_code(obs, "code", system, code):
            vq = obs.get("valueQuantity")
            if vq:
                candidates.append((
                    _parse_date_key(effective),
                    obs,
                    vq.get("value"),
                    vq.get("unit"),
                ))
            continue

        for component in obs.get("component", []):
            if _has_code(component, "code", system, code):
                vq = component.get("valueQuantity")
                if vq:
                    candidates.append((
                        _parse_date_key(effective),
                        obs,
                        vq.get("value"),
                        vq.get("unit"),
                    ))

    if not candidates:
        return ExtractionResult(found=False)

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, obs, value, unit = candidates[0]

    return ExtractionResult(
        found=True,
        value=value,
        unit=unit,
        date=_get_effective_date(obs),
        fhir_reference=f"Observation/{obs.get('id', 'unknown')}",
        resource_type="Observation",
    )


@mlflow.trace(name="ips_extract_condition")
def extract_condition(
    ips_bundle: dict, system: str, code: str
) -> ExtractionResult:
    """Check if an active condition matching the code is present."""
    conditions = _get_resources(ips_bundle, "Condition")

    for condition in conditions:
        if not _has_code(condition, "code", system, code):
            continue

        clinical_status = condition.get("clinicalStatus", {})
        is_active = True
        for coding in clinical_status.get("coding", []):
            if coding.get("code") in ("resolved", "inactive", "remission"):
                is_active = False
                break

        if is_active:
            return ExtractionResult(
                found=True,
                value=True,
                fhir_reference=f"Condition/{condition.get('id', 'unknown')}",
                resource_type="Condition",
            )

    return ExtractionResult(found=False, value=False)


@mlflow.trace(name="ips_extract_medication")
def extract_medication(
    ips_bundle: dict, system: str, code: str
) -> ExtractionResult:
    """Check if an active medication matching the code is present."""
    for resource_type in ["MedicationStatement", "MedicationRequest"]:
        resources = _get_resources(ips_bundle, resource_type)
        for resource in resources:
            status = resource.get("status", "")
            if status in ("cancelled", "entered-in-error", "stopped"):
                continue

            if _has_code(resource, "medicationCodeableConcept", system, code):
                return ExtractionResult(
                    found=True,
                    value=True,
                    fhir_reference=f"{resource_type}/{resource.get('id', 'unknown')}",
                    resource_type=resource_type,
                )

    return ExtractionResult(found=False, value=False)


@mlflow.trace(name="ips_extract_allergy")
def extract_allergy(
    ips_bundle: dict, system: str, code: str
) -> ExtractionResult:
    """Check if an active allergy matching the code is present."""
    allergies = _get_resources(ips_bundle, "AllergyIntolerance")

    for allergy in allergies:
        if not _has_code(allergy, "code", system, code):
            continue

        clinical_status = allergy.get("clinicalStatus", {})
        is_active = True
        for coding in clinical_status.get("coding", []):
            if coding.get("code") in ("resolved", "inactive"):
                is_active = False
                break

        if is_active:
            return ExtractionResult(
                found=True,
                value=True,
                fhir_reference=f"AllergyIntolerance/{allergy.get('id', 'unknown')}",
                resource_type="AllergyIntolerance",
            )

    return ExtractionResult(found=False, value=False)
