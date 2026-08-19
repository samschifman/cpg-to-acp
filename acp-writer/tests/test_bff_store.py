from datetime import datetime, timedelta, timezone

import pytest

from acp_writer.mocks.store import AUTO_DURATION, Store
from acp_writer.services import bff_models as m


class FakeClock:
    def __init__(self, t: datetime):
        self.t = t

    def __call__(self) -> datetime:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.fixture
def store(clock):
    return Store(clock=clock)


def test_new_run_is_running_with_first_step_active(store):
    run = store.create_run({"resourceType": "Bundle"})
    detail = store.to_detail(run)
    assert detail.status == m.RunStatus.running
    assert detail.current_steps == [m.StepKey.scan_patient]
    assert detail.care_plan is None


def test_run_reaches_gate_after_auto_duration(store, clock):
    run = store.create_run({"resourceType": "Bundle"})
    clock.advance(AUTO_DURATION.total_seconds() + 1)
    detail = store.to_detail(run)
    assert detail.status == m.RunStatus.awaiting_careplan_review
    assert detail.awaiting_review == m.ReviewGate.careplan
    assert detail.care_plan is not None
    assert detail.current_steps == [m.StepKey.review_careplan]


def test_approve_completes_and_persists_careplan(store, clock):
    run = store.create_run({"resourceType": "Bundle"})
    clock.advance(AUTO_DURATION.total_seconds() + 1)
    store.submit_review(run.run_id, m.ReviewAction(decision=m.ReviewDecision.approve))
    detail = store.to_detail(run)
    assert detail.status == m.RunStatus.completed
    assert detail.careplan_id is not None
    assert detail.careplan_id in store.careplans


def test_request_changes_loops_with_iteration_and_feedback(store, clock):
    run = store.create_run({"resourceType": "Bundle"})
    clock.advance(AUTO_DURATION.total_seconds() + 1)
    action = m.ReviewAction(
        decision=m.ReviewDecision.request_changes,
        feedback=[m.FeedbackItem(item_id="goal-1", comment="tighten BP target")],
    )
    store.submit_review(run.run_id, action)
    # back to running
    assert store.to_detail(run).status == m.RunStatus.running
    # advance to the gate again
    clock.advance(AUTO_DURATION.total_seconds() + 1)
    detail = store.to_detail(run)
    assert detail.status == m.RunStatus.awaiting_careplan_review
    assert detail.review_iteration == 1
    assert detail.previous_feedback.feedback[0].item_id == "goal-1"


def test_review_before_gate_raises(store):
    run = store.create_run({"resourceType": "Bundle"})
    with pytest.raises(ValueError):
        store.submit_review(run.run_id, m.ReviewAction(decision=m.ReviewDecision.approve))


def test_cancel(store):
    run = store.create_run({"resourceType": "Bundle"})
    assert store.cancel(run.run_id) is True
    assert store.to_detail(run).status == m.RunStatus.cancelled
    assert store.cancel("run-nope") is False


def test_gate_at_exact_auto_duration_boundary(store, clock):
    run = store.create_run({"resourceType": "Bundle"})
    clock.advance(AUTO_DURATION.total_seconds())  # exactly at the boundary
    assert store.to_detail(run).status == m.RunStatus.awaiting_careplan_review


def test_cancelled_run_freezes_progress(store, clock):
    run = store.create_run({"resourceType": "Bundle"})
    clock.advance(2 * 2 + 0.1)  # ~2 automated steps done
    store.cancel(run.run_id)
    done_after_cancel = sum(s.status == m.StepStatus.done for s in store.to_detail(run).steps)
    clock.advance(1000)  # poll much later
    done_much_later = sum(s.status == m.StepStatus.done for s in store.to_detail(run).steps)
    assert store.to_detail(run).status == m.RunStatus.cancelled
    assert done_much_later == done_after_cancel  # frozen, not still advancing


def test_multiple_request_changes_rounds(store, clock):
    run = store.create_run({"resourceType": "Bundle"})
    for i in range(1, 3):  # two rounds
        clock.advance(AUTO_DURATION.total_seconds() + 1)
        store.submit_review(
            run.run_id,
            m.ReviewAction(
                decision=m.ReviewDecision.request_changes,
                feedback=[m.FeedbackItem(item_id="goal-1", comment=f"round {i}")],
            ),
        )
        assert store.to_detail(run).status == m.RunStatus.running
    clock.advance(AUTO_DURATION.total_seconds() + 1)
    detail = store.to_detail(run)
    assert detail.review_iteration == 2
    assert detail.previous_feedback.feedback[0].comment == "round 2"
