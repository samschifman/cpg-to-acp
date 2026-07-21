"""Tests for the IPS Extractor tool."""

import json
from pathlib import Path

from acp_writer.tools.ips_extractor import (
    extract_allergy,
    extract_condition,
    extract_medication,
    extract_observation,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "mock-EHR" / "data"

SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"


def _load_bundle(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text())


class TestExtractObservation:
    def test_systolic_bp_from_component(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_observation(bundle, LOINC, "8480-6")
        assert result.found
        assert result.value == 142
        assert result.unit == "mmHg"
        assert result.fhir_reference == "Observation/observation-bp-1"

    def test_diastolic_bp_from_component(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_observation(bundle, LOINC, "8462-4")
        assert result.found
        assert result.value == 92

    def test_lifestyle_patient_bp(self):
        bundle = _load_bundle("patient-bundle-lifestyle.json")
        result = extract_observation(bundle, LOINC, "8480-6")
        assert result.found
        assert result.value == 125

    def test_missing_observation(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_observation(bundle, LOINC, "2345-7")  # glucose
        assert not result.found

    def test_returns_fhir_reference(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_observation(bundle, LOINC, "8480-6")
        assert result.fhir_reference.startswith("Observation/")
        assert result.resource_type == "Observation"

    def test_returns_date(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_observation(bundle, LOINC, "8480-6")
        assert result.date is not None
        assert "2026" in result.date

    def test_empty_bundle(self):
        result = extract_observation({"entry": []}, LOINC, "8480-6")
        assert not result.found

    def test_most_recent_selected(self):
        bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "old",
                        "status": "final",
                        "effectiveDateTime": "2026-01-01",
                        "code": {"coding": [{"system": LOINC, "code": "8480-6"}]},
                        "valueQuantity": {"value": 130, "unit": "mmHg"},
                    },
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "new",
                        "status": "final",
                        "effectiveDateTime": "2026-07-01",
                        "code": {"coding": [{"system": LOINC, "code": "8480-6"}]},
                        "valueQuantity": {"value": 145, "unit": "mmHg"},
                    },
                },
            ],
        }
        result = extract_observation(bundle, LOINC, "8480-6")
        assert result.value == 145
        assert result.fhir_reference == "Observation/new"


class TestExtractCondition:
    def test_hypertension_present(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_condition(bundle, SNOMED, "59621000")
        assert result.found
        assert result.value is True
        assert result.fhir_reference == "Condition/condition-htn-1"

    def test_diabetes_present(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_condition(bundle, SNOMED, "44054006")
        assert result.found

    def test_diabetes_absent_lifestyle(self):
        bundle = _load_bundle("patient-bundle-lifestyle.json")
        result = extract_condition(bundle, SNOMED, "44054006")
        assert not result.found
        assert result.value is False

    def test_resolved_condition_excluded(self):
        bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "c1",
                        "clinicalStatus": {
                            "coding": [{"code": "resolved"}],
                        },
                        "code": {"coding": [{"system": SNOMED, "code": "12345"}]},
                    },
                },
            ],
        }
        result = extract_condition(bundle, SNOMED, "12345")
        assert not result.found

    def test_missing_condition(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_condition(bundle, SNOMED, "9999999")
        assert not result.found


class TestExtractMedication:
    def test_metformin_present(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_medication(bundle, RXNORM, "860975")
        assert result.found
        assert result.fhir_reference == "MedicationStatement/medstmt-metformin-1"

    def test_medication_absent_lifestyle(self):
        bundle = _load_bundle("patient-bundle-lifestyle.json")
        result = extract_medication(bundle, RXNORM, "860975")
        assert not result.found

    def test_cancelled_medication_excluded(self):
        bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "MedicationRequest",
                        "id": "m1",
                        "status": "cancelled",
                        "medicationCodeableConcept": {
                            "coding": [{"system": RXNORM, "code": "12345"}],
                        },
                    },
                },
            ],
        }
        result = extract_medication(bundle, RXNORM, "12345")
        assert not result.found

    def test_medication_request_found(self):
        bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "MedicationRequest",
                        "id": "mr1",
                        "status": "active",
                        "medicationCodeableConcept": {
                            "coding": [{"system": RXNORM, "code": "29046"}],
                        },
                    },
                },
            ],
        }
        result = extract_medication(bundle, RXNORM, "29046")
        assert result.found
        assert result.resource_type == "MedicationRequest"


class TestExtractAllergy:
    def test_allergy_present(self):
        bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "AllergyIntolerance",
                        "id": "a1",
                        "clinicalStatus": {
                            "coding": [{"code": "active"}],
                        },
                        "code": {"coding": [{"system": SNOMED, "code": "91936005"}]},
                    },
                },
            ],
        }
        result = extract_allergy(bundle, SNOMED, "91936005")
        assert result.found
        assert result.fhir_reference == "AllergyIntolerance/a1"

    def test_allergy_absent(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_allergy(bundle, SNOMED, "91936005")
        assert not result.found

    def test_resolved_allergy_excluded(self):
        bundle = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "AllergyIntolerance",
                        "id": "a1",
                        "clinicalStatus": {
                            "coding": [{"code": "resolved"}],
                        },
                        "code": {"coding": [{"system": SNOMED, "code": "91936005"}]},
                    },
                },
            ],
        }
        result = extract_allergy(bundle, SNOMED, "91936005")
        assert not result.found


class TestToDict:
    def test_found_observation(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_observation(bundle, LOINC, "8480-6")
        d = result.to_dict()
        assert d["found"] is True
        assert d["value"] == 142
        assert d["unit"] == "mmHg"
        assert "fhir_reference" in d

    def test_not_found(self):
        bundle = _load_bundle("patient-bundle-medication.json")
        result = extract_observation(bundle, LOINC, "99999-9")
        d = result.to_dict()
        assert d["found"] is False
        assert "value" not in d
