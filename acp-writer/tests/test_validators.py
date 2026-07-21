"""Tests for FHIR syntax and terminology validators."""

from datetime import datetime, timezone

from acp_writer.nodes.fhir_syntax_validator import fhir_syntax_validator
from acp_writer.nodes.terminology_validator import terminology_validator
from acp_writer.planning_brief import (
    ActivityType,
    DMNAuditEntry,
    FHIRCode,
    PlanActivity,
    PlanGoal,
    PlanningBrief,
    ReviewStatus,
    TargetValue,
)
from acp_writer.validators.fhir_bundle_builder import build_fhir_bundle
from acp_writer.validators.fhir_syntax import validate_fhir_bundle


def _valid_bundle() -> dict:
    brief = PlanningBrief(
        patient_reference="Patient/patient-1",
        applicable_cpgs=["SYN-HTN-2026-001"],
        goals=[
            PlanGoal(
                description="Lower BP",
                target_measure_code=FHIRCode(system="http://loinc.org", code="8480-6"),
                target_value=TargetValue(high=140, unit="mmHg"),
                source_cpg="SYN-HTN-2026-001",
            ),
        ],
        activities=[
            PlanActivity(
                type=ActivityType.MEDICATION,
                description="Lisinopril 10mg",
                code=FHIRCode(system="http://www.nlm.nih.gov/research/umls/rxnorm", code="29046", display="Lisinopril"),
                dose="10 mg",
                source_recommendation_id="rec-1",
                source_cpg="SYN-HTN-2026-001",
            ),
        ],
        review_status=ReviewStatus.APPROVED,
    )
    return build_fhir_bundle(brief)


class TestFHIRSyntaxValidation:
    def test_valid_bundle_passes(self):
        errors = validate_fhir_bundle(_valid_bundle())
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_resource_type(self):
        errors = validate_fhir_bundle({"type": "transaction", "entry": []})
        assert any("resourceType" in e for e in errors)

    def test_missing_type(self):
        errors = validate_fhir_bundle({"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Patient", "id": "1"}}]})
        assert any("type" in e for e in errors)

    def test_empty_entries(self):
        errors = validate_fhir_bundle({"resourceType": "Bundle", "type": "transaction", "entry": []})
        assert any("no entries" in e.lower() for e in errors)

    def test_missing_id(self):
        bundle = _valid_bundle()
        del bundle["entry"][0]["resource"]["id"]
        errors = validate_fhir_bundle(bundle)
        assert any("missing id" in e.lower() for e in errors)

    def test_missing_transaction_request(self):
        bundle = _valid_bundle()
        del bundle["entry"][0]["request"]
        errors = validate_fhir_bundle(bundle)
        assert any("request" in e.lower() for e in errors)

    def test_missing_careplan_status(self):
        bundle = _valid_bundle()
        for entry in bundle["entry"]:
            if entry["resource"]["resourceType"] == "CarePlan":
                del entry["resource"]["status"]
                break
        errors = validate_fhir_bundle(bundle)
        assert any("status" in e.lower() for e in errors)

    def test_ai_transparency_checks(self):
        bundle = _valid_bundle()
        for entry in bundle["entry"]:
            if entry["resource"]["resourceType"] == "Device":
                bundle["entry"].remove(entry)
                break
        errors = validate_fhir_bundle(bundle)
        assert any("AI-Device" in e for e in errors)

    def test_missing_aiast_tag(self):
        bundle = _valid_bundle()
        bundle["entry"][0]["resource"]["meta"]["security"] = []
        errors = validate_fhir_bundle(bundle)
        assert any("AIAST" in e for e in errors)

    def test_unresolved_reference(self):
        bundle = _valid_bundle()
        for entry in bundle["entry"]:
            if entry["resource"]["resourceType"] == "CarePlan":
                entry["resource"]["goal"] = [{"reference": "urn:uuid:nonexistent"}]
                break
        errors = validate_fhir_bundle(bundle)
        assert any("Unresolved" in e for e in errors)


class TestFHIRSyntaxValidatorNode:
    def test_valid_bundle(self):
        result = fhir_syntax_validator({"fhir_bundle": _valid_bundle()})
        assert result["syntax_errors"] == []

    def test_invalid_bundle(self):
        bundle = _valid_bundle()
        del bundle["entry"][0]["resource"]["id"]
        result = fhir_syntax_validator({"fhir_bundle": bundle})
        assert len(result["syntax_errors"]) > 0

    def test_empty_bundle(self):
        result = fhir_syntax_validator({"fhir_bundle": {"entry": []}})
        assert result["syntax_errors"] == []


class TestTerminologyValidatorNode:
    def test_empty_bundle(self):
        result = terminology_validator({"fhir_bundle": {"entry": []}})
        assert result["terminology_issues"] == []

    def test_with_valid_bundle(self):
        result = terminology_validator({"fhir_bundle": _valid_bundle()})
        assert isinstance(result["terminology_issues"], list)
