"""Integration tests for the acp-writer API.

Requires Kogito decision service running on localhost:8081.
Start with: podman-compose up -d kogito acp-writer
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from acp_writer.api import app, _dynamic_models

PROJECT_ROOT = Path(__file__).parent.parent.parent

client = TestClient(app)


def load_bundle(name: str) -> dict:
    path = PROJECT_ROOT / "mock-EHR" / "data" / name
    return json.loads(path.read_text())


def load_dmn(name: str) -> str:
    path = PROJECT_ROOT / "cpg-ingester" / "data" / "golden" / name
    return path.read_text()


def deploy_models():
    """Deploy the standard hypertension DMN models for tests that need them."""
    for dmn_file in ["treatment-recommendation.dmn", "monitoring-plan.dmn"]:
        dmn_xml = load_dmn(dmn_file)
        r = client.post(
            "/api/v1/decisions/models",
            content=dmn_xml,
            headers={"Content-Type": "application/xml"},
        )
        assert r.status_code == 201


def find_resources(bundle: dict, resource_type: str) -> list[dict]:
    return [
        e["resource"]
        for e in bundle.get("entry", [])
        if e.get("resource", {}).get("resourceType") == resource_type
    ]


@pytest.fixture(autouse=True)
def clear_models():
    """Clear dynamic models between tests."""
    _dynamic_models.clear()
    yield
    _dynamic_models.clear()


class TestHealth:
    def test_liveness(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "UP"

    def test_status(self):
        r = client.get("/api/v1/status")
        assert r.status_code == 200
        data = r.json()
        assert "decision_engine" in data
        assert "knowledge_base" in data


class TestDecisionModels:
    def test_list_empty(self):
        r = client.get("/api/v1/decisions/models")
        assert r.status_code == 200
        assert r.json() == []

    def test_deploy_model(self):
        dmn_xml = load_dmn("treatment-recommendation.dmn")
        r = client.post(
            "/api/v1/decisions/models",
            content=dmn_xml,
            headers={"Content-Type": "application/xml"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Treatment Recommendation"
        assert data["id"] == "treatment-recommendation"
        assert len(data["inputs"]) == 3
        assert len(data["outputs"]) == 4

    def test_list_after_deploy(self):
        deploy_models()
        r = client.get("/api/v1/decisions/models")
        assert r.status_code == 200
        models = r.json()
        assert len(models) == 2

    def test_get_model(self):
        deploy_models()
        r = client.get("/api/v1/decisions/models/treatment-recommendation")
        assert r.status_code == 200
        data = r.json()
        assert "dmn_xml" in data

    def test_delete_model(self):
        deploy_models()
        r = client.delete("/api/v1/decisions/models/treatment-recommendation")
        assert r.status_code == 204
        r = client.get("/api/v1/decisions/models")
        assert len(r.json()) == 1

    def test_deploy_invalid_xml(self):
        r = client.post(
            "/api/v1/decisions/models",
            content="not xml",
            headers={"Content-Type": "application/xml"},
        )
        assert r.status_code == 400


@pytest.mark.integration
class TestCarePlanGeneration:
    """These tests require Kogito running on localhost:8081."""

    def test_medication_path(self):
        deploy_models()
        bundle = load_bundle("patient-bundle-medication.json")
        r = client.post(
            "/api/v1/careplans",
            json=bundle,
            headers={"Content-Type": "application/fhir+json"},
        )
        assert r.status_code == 201

        careplan_bundle = r.json()
        assert careplan_bundle["resourceType"] == "Bundle"

        careplans = find_resources(careplan_bundle, "CarePlan")
        assert len(careplans) == 1
        assert careplans[0]["title"] == "Hypertension Management Plan"

        goals = find_resources(careplan_bundle, "Goal")
        assert len(goals) == 1

        med_requests = find_resources(careplan_bundle, "MedicationRequest")
        assert len(med_requests) == 1
        assert "Lisinopril" in med_requests[0]["medicationCodeableConcept"]["text"]

        service_requests = find_resources(careplan_bundle, "ServiceRequest")
        assert len(service_requests) == 2
        sr_texts = {sr["code"]["text"] for sr in service_requests}
        assert "Follow-up appointment" in sr_texts
        assert "Basic Metabolic Panel" in sr_texts

    def test_lifestyle_path(self):
        deploy_models()
        bundle = load_bundle("patient-bundle-lifestyle.json")
        r = client.post(
            "/api/v1/careplans",
            json=bundle,
            headers={"Content-Type": "application/fhir+json"},
        )
        assert r.status_code == 201

        careplan_bundle = r.json()
        med_requests = find_resources(careplan_bundle, "MedicationRequest")
        assert len(med_requests) == 0

        service_requests = find_resources(careplan_bundle, "ServiceRequest")
        assert len(service_requests) == 1
        assert service_requests[0]["code"]["text"] == "Follow-up appointment"
        assert service_requests[0]["occurrenceTiming"]["repeat"]["period"] == 12

    def test_no_models_deployed(self):
        bundle = load_bundle("patient-bundle-medication.json")
        r = client.post("/api/v1/careplans", json=bundle)
        assert r.status_code == 422

    def test_invalid_bundle(self):
        r = client.post("/api/v1/careplans", json={"not": "a bundle"})
        assert r.status_code == 400

    def test_no_patient_in_bundle(self):
        r = client.post(
            "/api/v1/careplans",
            json={"resourceType": "Bundle", "type": "collection", "entry": []},
        )
        assert r.status_code == 400

    def test_no_bp_observation(self):
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "test-patient"}},
            ],
        }
        r = client.post("/api/v1/careplans", json=bundle)
        assert r.status_code == 400
        assert "blood pressure" in r.json()["detail"].lower()


class TestCarePlanStubs:
    def test_list_careplans_not_implemented(self):
        r = client.get("/api/v1/careplans")
        assert r.status_code == 501

    def test_get_careplan_not_implemented(self):
        r = client.get("/api/v1/careplans/some-id")
        assert r.status_code == 501

    def test_update_status_not_implemented(self):
        r = client.put("/api/v1/careplans/some-id/status", json={"status": "approved"})
        assert r.status_code == 501


class TestKnowledgeStubs:
    def test_ingest_not_implemented(self):
        r = client.post("/api/v1/knowledge/documents", json={})
        assert r.status_code == 501

    def test_search_not_implemented(self):
        r = client.post("/api/v1/knowledge/search", json={"query": "test"})
        assert r.status_code == 501
