"""Tests for CarePlanComposerState."""

from acp_writer.state import CarePlanComposerState


class TestCarePlanComposerState:
    def test_create_empty(self):
        state: CarePlanComposerState = {}
        assert state == {}

    def test_create_with_fields(self):
        state: CarePlanComposerState = {
            "run_id": "test-001",
            "ips_bundle": {"resourceType": "Bundle"},
            "litellm_url": "http://localhost:4000",
            "llm_model": "gpt-4",
        }
        assert state["run_id"] == "test-001"
        assert state["ips_bundle"]["resourceType"] == "Bundle"

    def test_phase1_outputs(self):
        state: CarePlanComposerState = {
            "condition_codes": [{"system": "http://snomed.info/sct", "code": "38341003"}],
            "medication_codes": [],
            "allergy_codes": [],
            "planning_brief": {"patient_reference": "Patient/123"},
        }
        assert len(state["condition_codes"]) == 1
        assert state["planning_brief"]["patient_reference"] == "Patient/123"

    def test_phase2_outputs(self):
        state: CarePlanComposerState = {
            "fhir_bundle": {"resourceType": "Bundle", "type": "transaction"},
            "syntax_errors": [],
            "terminology_issues": [],
            "delivery_status": "success",
        }
        assert state["fhir_bundle"]["type"] == "transaction"
        assert state["delivery_status"] == "success"
