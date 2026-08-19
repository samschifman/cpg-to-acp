"""Smoke test: the module-level `app` boots and serves in mock mode via ASGI."""

from starlette.testclient import TestClient

from acp_writer.services.bff import app


def test_module_app_boots_in_mock_mode():
    with TestClient(app) as client:  # runs startup/shutdown lifecycle
        health = client.get("/health").json()
        assert health["status"] == "UP"
        assert health["mock"] is True
        # seed data is present on the module-level app
        statuses = {r["status"] for r in client.get("/api/v1/runs").json()}
        assert "completed" in statuses
        assert "awaiting_careplan_review" in statuses
