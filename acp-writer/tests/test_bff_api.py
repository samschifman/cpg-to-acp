from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from acp_writer.mocks.router import build_router, seed
from acp_writer.mocks.store import AUTO_DURATION, Store
from acp_writer.services import bff_models as m


class FakeClock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.fixture
def client(clock):
    from fastapi import FastAPI
    app = FastAPI()
    store = Store(clock=clock)
    seed(store)
    app.include_router(build_router(store))
    app.state.store = store
    return TestClient(app)


def test_status(client):
    r = client.get("/api/v1/status")
    assert r.status_code == 200
    assert r.json()["decisionEngine"]["available"] is True


def test_seed_dashboard_has_completed_and_gate_runs(client):
    r = client.get("/api/v1/runs")
    assert r.status_code == 200
    statuses = {row["status"] for row in r.json()}
    assert "completed" in statuses
    assert "awaiting_careplan_review" in statuses


def test_seed_completed_run_has_a_careplan(client):
    assert len(client.get("/api/v1/careplans").json()) >= 1


def test_create_run_then_reach_gate(client, clock):
    run_id = client.post("/api/v1/runs", json={"ipsBundle": {"resourceType": "Bundle"}}).json()["runId"]
    assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == "running"
    clock.advance(AUTO_DURATION.total_seconds() + 1)
    detail = client.get(f"/api/v1/runs/{run_id}").json()
    assert detail["status"] == "awaiting_careplan_review"
    assert detail["carePlan"]["goals"][0]["id"] == "goal-1"


def test_approve_flow(client, clock):
    run_id = client.post("/api/v1/runs", json={"ipsBundle": {}}).json()["runId"]
    clock.advance(AUTO_DURATION.total_seconds() + 1)
    r = client.post(f"/api/v1/runs/{run_id}/review/careplan", json={"decision": "approve"})
    assert r.status_code == 202
    assert r.json()["status"] == "completed"
    assert r.json()["careplanId"]


def test_request_changes_returns_409_before_gate(client):
    run_id = client.post("/api/v1/runs", json={"ipsBundle": {}}).json()["runId"]
    r = client.post(f"/api/v1/runs/{run_id}/review/careplan", json={"decision": "approve"})
    assert r.status_code == 409


def test_get_missing_run_404(client):
    assert client.get("/api/v1/runs/run-nope").status_code == 404


def test_cancel(client):
    run_id = client.post("/api/v1/runs", json={"ipsBundle": {}}).json()["runId"]
    assert client.delete(f"/api/v1/runs/{run_id}").status_code == 204
    assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == "cancelled"


def test_seed_has_failed_run(client):
    statuses = {r["status"] for r in client.get("/api/v1/runs").json()}
    assert "failed" in statuses
