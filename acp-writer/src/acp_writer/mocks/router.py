"""Mock API router implementing the PR #127 UI contract with canned data."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query

from acp_writer.mocks.store import AUTO_DURATION, Store
from acp_writer.services import bff_models as m


def seed(store: Store) -> None:
    """Populate a couple of runs so the dashboard is non-empty on first load."""
    now = store.now()
    # A: completed (approved) — created well in the past, then approved.
    a = store.create_run({"resourceType": "Bundle"})
    a.created_at = now - timedelta(minutes=30)
    a.effective_start = now - timedelta(minutes=30)
    store.submit_review(a.run_id, m.ReviewAction(decision=m.ReviewDecision.approve))
    # B: pinned at the care-plan gate — reliably viewable for review-UI work.
    b = store.create_run({"resourceType": "Bundle"})
    b.created_at = now - timedelta(minutes=5)
    b.effective_start = now - AUTO_DURATION - timedelta(seconds=1)


def build_router(store: Store) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/runs", response_model=m.RunCreated, status_code=202)
    def create_run(body: m.CreateRunRequest):
        run = store.create_run(body.ips_bundle)
        return m.RunCreated(run_id=run.run_id, status=store._status(run))

    @router.get("/runs", response_model=list[m.RunSummary])
    def list_runs(status: m.RunStatus | None = None, limit: int = Query(default=50, ge=1)):
        rows = store.list_summaries()
        if status is not None:
            rows = [r for r in rows if r.status == status]
        return rows[:limit]

    @router.get("/runs/{run_id}", response_model=m.RunDetail)
    def get_run(run_id: str):
        run = store.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return store.to_detail(run)

    @router.delete("/runs/{run_id}", status_code=204)
    def cancel_run(run_id: str):
        if not store.cancel(run_id):
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    @router.post("/runs/{run_id}/review/careplan", response_model=m.RunDetail, status_code=202)
    def submit_review(run_id: str, action: m.ReviewAction):
        try:
            run = store.submit_review(run_id, action)
        except ValueError:
            raise HTTPException(status_code=409, detail="Run is not awaiting care-plan review")
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return store.to_detail(run)

    @router.get("/careplans", response_model=list[m.CarePlanSummary])
    def list_careplans():
        # response_model=list[CarePlanSummary] intentionally drops CarePlanDetail's patient/view — the list endpoint must not leak the full plan.
        return list(store.careplans.values())

    @router.get("/careplans/{careplan_id}", response_model=m.CarePlanDetail)
    def get_careplan(careplan_id: str):
        cp = store.careplans.get(careplan_id)
        if not cp:
            raise HTTPException(status_code=404, detail=f"Care plan {careplan_id} not found")
        return cp

    @router.get("/status", response_model=m.SystemStatus)
    def system_status():
        return m.SystemStatus(
            version="mock-0.1.0",
            decision_engine=m.DecisionEngineStatus(available=True, models_deployed=4),
            knowledge_base=m.KnowledgeBaseStatus(available=True, guidelines=3, recommendations=42),
        )

    return router
