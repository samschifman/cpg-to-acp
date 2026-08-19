"""In-memory run store for the mock BFF.

Progression is derived from an injectable clock: given a run's effective start
time and the elapsed seconds, we compute which pipeline steps are done/active and
whether the run has reached the care-plan gate. This keeps the mock deterministic
and testable (inject a fake clock) with no background threads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

from acp_writer.services import bff_models as m

# Ordered automated pipeline (human gate `review_careplan` handled separately).
AUTO_STEPS: list[m.StepKey] = [
    m.StepKey.scan_patient,
    m.StepKey.resolve_guidelines,
    m.StepKey.execute_dmn,
    m.StepKey.retrieve_recommendations,
    m.StepKey.compose_plan,
    m.StepKey.generate_bundle,
    m.StepKey.review_fhir,
]
STEP_SECONDS = 2  # each automated step takes this long in the mock timeline
AUTO_DURATION = timedelta(seconds=STEP_SECONDS * len(AUTO_STEPS))


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Run:
    run_id: str
    patient: m.PatientSummary
    care_plan: m.CarePlanView
    created_at: datetime
    effective_start: datetime           # progression clock origin (resets on request_changes)
    review_iteration: int = 0
    previous_feedback: m.ReviewAction | None = None
    # terminal / gate overrides; when None, status is time-derived
    pinned_status: m.RunStatus | None = None
    frozen_at: datetime | None = None   # freezes progression clock (set on cancel)
    careplan_id: str | None = None


class Store:
    def __init__(self, clock: Callable[[], datetime] = _default_clock):
        self._clock = clock
        self.runs: dict[str, Run] = {}
        self.careplans: dict[str, m.CarePlanDetail] = {}

    # -- test/seed helpers --
    def set_clock(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    def _iso(self, dt: datetime) -> str:
        return dt.isoformat()

    # -- lifecycle --
    def create_run(self, ips_bundle: dict) -> Run:
        from acp_writer.mocks import data
        now = self._clock()
        run_id = f"run-{uuid4().hex[:8]}"
        run = Run(
            run_id=run_id,
            patient=data.make_patient_summary(ips_bundle),
            care_plan=data.make_care_plan_view(),
            created_at=now,
            effective_start=now,
        )
        self.runs[run_id] = run
        return run

    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    def cancel(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if not run:
            return False
        if self._status(run) in (m.RunStatus.completed, m.RunStatus.cancelled):
            return True  # already terminal; no-op
        run.frozen_at = self._clock()
        run.pinned_status = m.RunStatus.cancelled
        return True

    def submit_review(self, run_id: str, action: m.ReviewAction) -> Run | None:
        """Returns the run if it was at the gate; None if not found; raises
        ValueError if the run is not currently awaiting review (-> 409)."""
        run = self.runs.get(run_id)
        if not run:
            return None
        if self._status(run) != m.RunStatus.awaiting_careplan_review:
            raise ValueError("not awaiting review")
        if action.decision == m.ReviewDecision.approve:
            run.pinned_status = m.RunStatus.completed
            cp_id = f"cp-{uuid4().hex[:8]}"
            run.careplan_id = cp_id
            self.careplans[cp_id] = m.CarePlanDetail(
                id=cp_id,
                patient_name=run.patient.name,
                patient_reference=run.patient.patient_reference,
                status="active",
                generated_at=self._iso(self._clock()),
                run_id=run.run_id,
                patient=run.patient,
                view=run.care_plan,
            )
        else:  # request_changes -> regenerate; loop back to running
            run.previous_feedback = action
            run.review_iteration += 1
            run.effective_start = self._clock()
            run.pinned_status = None
        return run

    # -- progression --
    def _elapsed(self, run: Run) -> timedelta:
        end = run.frozen_at if run.frozen_at is not None else self._clock()
        return end - run.effective_start

    def _status(self, run: Run) -> m.RunStatus:
        if run.pinned_status is not None:
            return run.pinned_status
        if self._elapsed(run) >= AUTO_DURATION:
            return m.RunStatus.awaiting_careplan_review
        return m.RunStatus.running

    def _steps(self, run: Run) -> tuple[list[m.PipelineStep], list[m.StepKey]]:
        status = self._status(run)
        steps: list[m.PipelineStep] = []
        current: list[m.StepKey] = []

        if status in (m.RunStatus.awaiting_careplan_review, m.RunStatus.completed):
            n_done = len(AUTO_STEPS)
        elif status == m.RunStatus.cancelled:
            n_done = min(len(AUTO_STEPS), int(self._elapsed(run).total_seconds() // STEP_SECONDS))
        else:  # running
            n_done = min(len(AUTO_STEPS) - 1, int(self._elapsed(run).total_seconds() // STEP_SECONDS))

        for i, key in enumerate(AUTO_STEPS):
            if i < n_done:
                steps.append(m.PipelineStep(key=key, status=m.StepStatus.done))
            elif i == n_done and status == m.RunStatus.running:
                steps.append(m.PipelineStep(key=key, status=m.StepStatus.active))
                current.append(key)
            else:
                steps.append(m.PipelineStep(key=key, status=m.StepStatus.pending))

        # human gate
        if status == m.RunStatus.awaiting_careplan_review:
            steps.append(m.PipelineStep(key=m.StepKey.review_careplan, status=m.StepStatus.active))
            current.append(m.StepKey.review_careplan)
        elif status == m.RunStatus.completed:
            steps.append(m.PipelineStep(key=m.StepKey.review_careplan, status=m.StepStatus.done))
            steps.append(m.PipelineStep(key=m.StepKey.write_fhir, status=m.StepStatus.done))
            steps.append(m.PipelineStep(key=m.StepKey.done, status=m.StepStatus.done))
        else:
            steps.append(m.PipelineStep(key=m.StepKey.review_careplan, status=m.StepStatus.pending))

        return steps, current

    # -- view-model builders --
    def to_detail(self, run: Run) -> m.RunDetail:
        status = self._status(run)
        steps, current = self._steps(run)
        at_gate = status == m.RunStatus.awaiting_careplan_review
        return m.RunDetail(
            run_id=run.run_id,
            status=status,
            patient=run.patient,
            steps=steps,
            current_steps=current,
            awaiting_review=m.ReviewGate.careplan if at_gate else None,
            care_plan=run.care_plan if at_gate else None,
            review_iteration=run.review_iteration if at_gate else None,
            previous_feedback=run.previous_feedback if at_gate else None,
            careplan_id=run.careplan_id,
            created_at=self._iso(run.created_at),
            updated_at=self._iso(self._clock()),
        )

    def to_summary(self, run: Run) -> m.RunSummary:
        status = self._status(run)
        _, current = self._steps(run)
        return m.RunSummary(
            run_id=run.run_id,
            status=status,
            patient_name=run.patient.name,
            patient_reference=run.patient.patient_reference,
            current_steps=current,
            careplan_id=run.careplan_id,
            created_at=self._iso(run.created_at),
            updated_at=self._iso(self._clock()),
        )

    def list_summaries(self) -> list[m.RunSummary]:
        runs = sorted(self.runs.values(), key=lambda r: r.created_at, reverse=True)
        return [self.to_summary(r) for r in runs]
