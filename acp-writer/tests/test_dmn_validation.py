"""Tests for engine-backed DMN validation during model deployment."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from acp_writer.api import _dynamic_models, app
from acp_writer.services.decision_engine import app as decision_engine_app


client = TestClient(app)
decision_engine_client = TestClient(decision_engine_app)

VALIDATION_OK = {"valid": True, "messages": []}
VALIDATION_FAILED = {
    "valid": False,
    "messages": [{"severity": "ERROR", "text": "FEEL compilation failed"}],
}
DMN = """<?xml version="1.0"?><definitions xmlns="https://www.omg.org/spec/DMN/20211108/MODEL/" name="Test Model" id="test" namespace="https://example.test"><decision id="d" name="Decision"><variable name="Decision" typeRef="string"/><literalExpression><text>\"ok\"</text></literalExpression></decision></definitions>"""


@pytest.fixture(autouse=True)
def clear_models():
    _dynamic_models.clear()
    yield
    _dynamic_models.clear()


class TestApiDeploymentValidation:
    @patch("acp_writer.api._validate_dmn_with_engine", return_value=VALIDATION_FAILED)
    def test_invalid_model_returns_422_with_engine_messages(self, _validate):
        response = client.post("/api/v1/decisions/models", content=DMN)

        assert response.status_code == 422
        assert response.json() == {
            "error": "DMN engine validation failed",
            "messages": VALIDATION_FAILED["messages"],
        }
        assert _dynamic_models == {}

    @patch("acp_writer.api._validate_dmn_with_engine", return_value=VALIDATION_OK)
    def test_valid_model_is_deployed(self, _validate):
        response = client.post("/api/v1/decisions/models", content=DMN)

        assert response.status_code == 201
        assert response.json()["id"] == "test-model"
        _validate.assert_called_once_with(DMN)

    @patch("acp_writer.api._validate_dmn_with_engine", return_value=VALIDATION_OK)
    def test_validate_only_does_not_store_model(self, _validate):
        response = client.post("/api/v1/decisions/models?validate_only=true", content=DMN)

        assert response.status_code == 200
        assert response.json() == VALIDATION_OK
        assert _dynamic_models == {}

    @patch("acp_writer.api._validate_dmn_with_engine", return_value=None)
    def test_engine_unavailable_fails_open_for_deployment(self, _validate):
        response = client.post("/api/v1/decisions/models", content=DMN)

        assert response.status_code == 201
        assert response.json()["id"] == "test-model"

    @patch("acp_writer.api._validate_dmn_with_engine", return_value=None)
    def test_validate_only_reports_engine_unavailable(self, _validate):
        response = client.post("/api/v1/decisions/models?validate_only=true", content=DMN)

        assert response.status_code == 503
        assert _dynamic_models == {}


class TestDecisionEngineDeploymentValidation:
    @patch("acp_writer.services.decision_engine._validate_dmn_with_engine", return_value=VALIDATION_FAILED)
    def test_pods_mode_returns_engine_messages(self, _validate):
        response = decision_engine_client.post("/api/v1/decisions/models", content=DMN)

        assert response.status_code == 422
        assert response.json()["messages"] == VALIDATION_FAILED["messages"]
        assert _dynamic_models == {}

    @patch("acp_writer.services.decision_engine._validate_dmn_with_engine", return_value=VALIDATION_OK)
    def test_pods_mode_validate_only_does_not_store(self, _validate):
        response = decision_engine_client.post(
            "/api/v1/decisions/models?validate_only=true", content=DMN)

        assert response.status_code == 200
        assert response.json() == VALIDATION_OK
        assert _dynamic_models == {}
