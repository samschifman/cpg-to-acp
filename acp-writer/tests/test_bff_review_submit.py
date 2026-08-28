"""Endpoint tests for POST /api/v1/runs/{id}/review/{gate}.

Covers the truthful-failure behavior added for #169: the BFF must never leak a
raw 500 when the workflow engine is briefly unavailable (devmode live-reload),
and must not let a duplicate submit be silently dropped by the engine during the
6-24s window before the run leaves the review gate.

  - engine send_review raises -> 503 with a friendly message
  - duplicate submit while the first is pending -> 409
  - once the run leaves the gate, a fresh round's submit is accepted again
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from acp_writer.services import bff


def _instance(workflowdata: dict) -> dict:
    return {
        "id": "sf-1",
        "status": "ACTIVE",
        "startDate": "2026-01-01T00:00:00Z",
        "workflowdata": workflowdata,
    }


# fhirReviewData present, no careplanReview/writeResult -> ReviewCarePlan gate.
AT_GATE = _instance({"fhirReviewData": {"completed_at": "2026-01-01T01:00:00Z"}})
# approve consumed -> WriteFHIR, run no longer awaiting the careplan gate.
PAST_GATE = _instance(
    {
        "fhirReviewData": {"completed_at": "2026-01-01T01:00:00Z"},
        "careplanReview": {"decision": "approve", "completed_at": "2026-01-01T02:00:00Z"},
    }
)


class FakeSonataFlow:
    """Minimal stand-in for SonataFlowClient; `instance` is what get_instance returns."""

    def __init__(self, instance: dict):
        self.instance = instance
        self.send_review = AsyncMock()

    async def get_instance(self, sf_id: str) -> dict:
        return self.instance


@pytest.fixture
def client(monkeypatch):
    fake = FakeSonataFlow(AT_GATE)
    monkeypatch.setattr(bff, "_sonataflow", fake)
    monkeypatch.setattr(bff, "_pending_reviews", {})
    monkeypatch.setattr(bff, "_pending_runs", {})
    tc = TestClient(bff.app)
    tc.fake = fake  # let tests reach the mock
    return tc


def test_engine_unavailable_returns_503(client):
    client.fake.send_review.side_effect = RuntimeError("Error Occurred After Shutdown")
    res = client.post("/api/v1/runs/run-1/review/careplan", json={"decision": "approve"})
    assert res.status_code == 503
    assert "temporarily unavailable" in res.json()["message"]


def test_duplicate_submit_while_pending_returns_409(client):
    first = client.post("/api/v1/runs/run-1/review/careplan", json={"decision": "approve"})
    assert first.status_code == 202
    # Run still reports awaitingReview=careplan (engine hasn't advanced yet).
    second = client.post("/api/v1/runs/run-1/review/careplan", json={"decision": "approve"})
    assert second.status_code == 409
    assert "already submitted" in second.json()["message"]
    # The engine must not have been asked to consume the duplicate.
    assert client.fake.send_review.await_count == 1


def test_submit_accepted_again_after_run_leaves_gate(client):
    first = client.post("/api/v1/runs/run-1/review/careplan", json={"decision": "request_changes",
                                                                     "comment": "tighten"})
    assert first.status_code == 202

    # Run advances off the gate; a poll observes it and clears the pending record.
    client.fake.instance = PAST_GATE
    client.get("/api/v1/runs/run-1")

    # Round 2 re-gates; a new submit must be accepted, not blocked as a duplicate.
    client.fake.instance = AT_GATE
    third = client.post("/api/v1/runs/run-1/review/careplan", json={"decision": "approve"})
    assert third.status_code == 202


def test_submit_when_not_awaiting_gate_returns_409(client):
    client.fake.instance = PAST_GATE
    res = client.post("/api/v1/runs/run-1/review/careplan", json={"decision": "approve"})
    assert res.status_code == 409
    assert "not awaiting" in res.json()["message"]
