# acp-writer mock BFF — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mock Backend-for-Frontend that satisfies the PR #127 UI contract (`acp-writer/api/bff-openapi.yaml`) with canned, deterministically-progressing data, so the acp-writer React UI — including the care-plan review loop — can be run locally and on-cluster without the real pipeline.

**Architecture:** One FastAPI app (`acp_writer.services.bff:app`) mirroring the cpg-ingester BFF's optional-backend pattern: when `SONATAFLOW_URL` is unset it mounts a mock router backed by an in-memory store. The store derives pipeline-step progress from an injectable clock so runs advance `running → awaiting_careplan_review → completed`. Contract-shaped Pydantic models are the reusable interface; the SonataFlow-backed branch is left a marked stub for the real BFF.

**Tech Stack:** Python 3.11+, FastAPI + Pydantic v2, uvicorn, pytest + Starlette `TestClient` (httpx), PyYAML (test-only), Helm (chart-pods), UBI9 Python 3.12 container.

**Base worktree:** `.claude/worktrees/acp-writer-bff` (branch `acp-writer-bff-mock`, off `bff-ui-contract`). All paths below are repo-relative. Run commands from `acp-writer/` unless noted.

**One-time setup (not a task):** `cd acp-writer && python -m venv .venv && . .venv/bin/activate && pip install -e '.[test]'`

---

## File Structure

| File | Responsibility |
|---|---|
| `acp-writer/src/acp_writer/services/bff_models.py` | Pydantic models + enums mirroring the contract (camelCase aliases). Reusable by the real BFF. |
| `acp-writer/src/acp_writer/mocks/__init__.py` | package marker |
| `acp-writer/src/acp_writer/mocks/data.py` | canned clinical content: a `PatientSummary`, a rich `CarePlanView`, a small valid FHIR bundle |
| `acp-writer/src/acp_writer/mocks/store.py` | in-memory run store + clock-derived step progression + review loop + careplan persistence |
| `acp-writer/src/acp_writer/mocks/router.py` | the 8 UI endpoints as an `APIRouter`, wiring HTTP ↔ store |
| `acp-writer/src/acp_writer/services/bff.py` | FastAPI app: mounts mock router (mock mode), `/health`, scoped CORS, stubbed real branch |
| `acp-writer/tests/test_bff_store.py` | store/progression unit tests (FakeClock) |
| `acp-writer/tests/test_bff_api.py` | endpoint behavior tests (TestClient) |
| `acp-writer/tests/test_bff_contract.py` | conformance: app paths == contract paths; models' aliases == contract schema properties |
| `acp-writer/deploy/pods/Containerfile.bff` | image for the `bff` pod |
| `acp-writer/deploy/chart-pods/values.yaml` | add the `bff` pod (modify) |
| `acp-writer/deploy/chart-pods/templates/deployments.yaml` | add `sonataflowUrl`/`minioEndpoint` env passthrough (modify) |
| `acp-writer/pyproject.toml` | add `pyyaml` to `[test]` extra (modify) |

**Import hygiene (hard rule):** `bff.py`, `bff_models.py`, and everything under `mocks/` may import only `fastapi`, `pydantic`, `starlette`, stdlib, and each other. They must NOT import `acp_writer.pipeline`, `.nodes.*`, `.services.llm_reasoning`, langchain, mlflow, etc. (`acp_writer/__init__.py` and `services/__init__.py` are empty, so this stays clean.)

---

## Task 1: Contract models

**Files:**
- Create: `acp-writer/src/acp_writer/services/bff_models.py`

- [ ] **Step 1: Write the models**

```python
"""Pydantic models mirroring acp-writer/api/bff-openapi.yaml (PR #127).

camelCase on the wire (aliases); snake_case in Python. Shared by the mock BFF
and reusable by the real SonataFlow-backed BFF.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ---- Enums ----
class RunStatus(str, Enum):
    running = "running"
    awaiting_careplan_review = "awaiting_careplan_review"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class StepStatus(str, Enum):
    pending = "pending"
    active = "active"
    done = "done"
    error = "error"
    skipped = "skipped"


class ReviewGate(str, Enum):
    careplan = "careplan"


class ReviewDecision(str, Enum):
    approve = "approve"
    request_changes = "request_changes"


class StepKey(str, Enum):
    scan_patient = "scan_patient"
    resolve_guidelines = "resolve_guidelines"
    execute_dmn = "execute_dmn"
    retrieve_recommendations = "retrieve_recommendations"
    compose_plan = "compose_plan"
    generate_bundle = "generate_bundle"
    review_fhir = "review_fhir"
    review_careplan = "review_careplan"
    write_fhir = "write_fhir"
    done = "done"


# ---- Clinical view-models ----
class CodedItem(_Model):
    display: str
    code: str | None = None
    system: str | None = None


class PatientSummary(_Model):
    name: str | None = None
    birth_date: str | None = None
    gender: str | None = None
    patient_reference: str | None = None
    conditions: list[CodedItem] = []
    medications: list[CodedItem] = []
    allergies: list[CodedItem] = []
    observations: list[CodedItem] = []


class PlanGoal(_Model):
    id: str
    description: str
    rationale: str | None = None
    source_cpg_id: str | None = None


class PlanActivity(_Model):
    id: str
    description: str
    goal_id: str | None = None
    detail: str | None = None


class PlanConflict(_Model):
    id: str
    severity: str | None = None  # info | warning | critical
    description: str


class CarePlanView(_Model):
    goals: list[PlanGoal] = []
    activities: list[PlanActivity] = []
    conflicts: list[PlanConflict] = []
    fhir_bundle: dict = {}


# ---- Review ----
class FeedbackItem(_Model):
    item_id: str
    comment: str


class ReviewAction(_Model):
    decision: ReviewDecision
    clinician: str | None = None
    comment: str | None = None
    feedback: list[FeedbackItem] = []


# ---- Runs ----
class RunCreated(_Model):
    run_id: str
    status: RunStatus


class PipelineStep(_Model):
    key: StepKey
    status: StepStatus
    started_at: str | None = None
    ended_at: str | None = None
    detail: str | None = None


class RunError(_Model):
    step_key: StepKey | None = None
    message: str | None = None


class RunSummary(_Model):
    run_id: str
    status: RunStatus
    patient_name: str | None = None
    patient_reference: str | None = None
    current_steps: list[StepKey] = []
    careplan_id: str | None = None
    created_at: str
    updated_at: str | None = None


class RunDetail(_Model):
    run_id: str
    status: RunStatus
    patient: PatientSummary | None = None
    steps: list[PipelineStep]
    current_steps: list[StepKey] = []
    awaiting_review: ReviewGate | None = None
    care_plan: CarePlanView | None = None
    review_iteration: int | None = None
    previous_feedback: ReviewAction | None = None
    careplan_id: str | None = None
    error: RunError | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ---- Care plans ----
class CarePlanSummary(_Model):
    id: str
    patient_name: str | None = None
    patient_reference: str | None = None
    status: str
    generated_at: str | None = None
    run_id: str | None = None


class CarePlanDetail(CarePlanSummary):
    patient: PatientSummary | None = None
    view: CarePlanView | None = None


# ---- System ----
class DecisionEngineStatus(_Model):
    available: bool
    models_deployed: int | None = None


class KnowledgeBaseStatus(_Model):
    available: bool
    guidelines: int | None = None
    recommendations: int | None = None


class SystemStatus(_Model):
    version: str | None = None
    decision_engine: DecisionEngineStatus | None = None
    knowledge_base: KnowledgeBaseStatus | None = None


class Error(_Model):
    message: str
    code: str | None = None


# ---- Request bodies ----
class CreateRunRequest(_Model):
    ips_bundle: dict
```

- [ ] **Step 2: Add `pyyaml` to the test extra**

Modify `acp-writer/pyproject.toml`, the `[project.optional-dependencies] test` list — add one line:

```toml
test = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    "pyyaml>=6.0",
]
```

Then re-install: `pip install -e '.[test]'`

- [ ] **Step 3: Write the model-conformance test**

Create `acp-writer/tests/test_bff_contract.py`:

```python
"""Contract conformance: our models/routes match acp-writer/api/bff-openapi.yaml."""

from pathlib import Path

import yaml

from acp_writer.services import bff_models as m

SPEC_PATH = Path(__file__).parents[2] / "acp-writer" / "api" / "bff-openapi.yaml"
# When run from the acp-writer/ dir the repo layout differs; resolve robustly:
if not SPEC_PATH.exists():
    SPEC_PATH = Path(__file__).parents[1] / "api" / "bff-openapi.yaml"


def _spec():
    return yaml.safe_load(SPEC_PATH.read_text())


def _schema_props(spec, name):
    return set(spec["components"]["schemas"][name]["properties"].keys())


def _model_aliases(model):
    return {f.alias or n for n, f in model.model_fields.items()}


def test_model_fields_match_contract_schemas():
    spec = _spec()
    pairs = {
        "CodedItem": m.CodedItem,
        "PatientSummary": m.PatientSummary,
        "PlanGoal": m.PlanGoal,
        "PlanActivity": m.PlanActivity,
        "PlanConflict": m.PlanConflict,
        "CarePlanView": m.CarePlanView,
        "FeedbackItem": m.FeedbackItem,
        "ReviewAction": m.ReviewAction,
        "RunCreated": m.RunCreated,
        "PipelineStep": m.PipelineStep,
        "RunError": m.RunError,
        "RunSummary": m.RunSummary,
        "RunDetail": m.RunDetail,
        "CarePlanSummary": m.CarePlanSummary,
        "SystemStatus": m.SystemStatus,
        "Error": m.Error,
    }
    mismatches = {}
    for name, model in pairs.items():
        want = _schema_props(spec, name)
        got = _model_aliases(model)
        if want != got:
            mismatches[name] = {"missing": sorted(want - got), "extra": sorted(got - want)}
    assert not mismatches, mismatches


def test_careplan_detail_is_summary_plus_patient_and_view():
    spec = _spec()
    summary = _schema_props(spec, "CarePlanSummary")
    # CarePlanDetail is allOf(CarePlanSummary, {patient, view})
    expected = summary | {"patient", "view"}
    assert _model_aliases(m.CarePlanDetail) == expected
```

- [ ] **Step 4: Run the conformance test — expect PASS**

Run: `pytest tests/test_bff_contract.py -v`
Expected: both tests PASS. If `test_model_fields_match_contract_schemas` reports mismatches, fix the model field names/aliases in `bff_models.py` until it passes (this is the harness doing its job).

- [ ] **Step 5: Commit**

```bash
git add acp-writer/src/acp_writer/services/bff_models.py acp-writer/tests/test_bff_contract.py acp-writer/pyproject.toml
git commit -m "Add contract models for acp-writer mock BFF"
```

---

## Task 2: In-memory store + progression

**Files:**
- Create: `acp-writer/src/acp_writer/mocks/__init__.py` (empty)
- Create: `acp-writer/src/acp_writer/mocks/store.py`
- Test: `acp-writer/tests/test_bff_store.py`

The store owns run lifecycle. Progression is derived from an injectable clock so tests are deterministic. `data.py` (Task 3) supplies the canned patient/careplan; to keep Task 2 self-contained, the store imports two factory functions from `data` that Task 3 creates — so **do Task 3's `data.py` before running Task 2's tests**, or stub them. (Plan order below builds `data.py` first in Task 3; Task 2 code references it.)

To avoid a forward-reference problem, Task 2 defines the store against a tiny protocol and Task 3 provides the data; the store imports `from acp_writer.mocks import data` lazily inside methods.

- [ ] **Step 1: Write the store**

Create `acp-writer/src/acp_writer/mocks/__init__.py` (empty file).

Create `acp-writer/src/acp_writer/mocks/store.py`:

```python
"""In-memory run store for the mock BFF.

Progression is derived from an injectable clock: given a run's effective start
time and the elapsed seconds, we compute which pipeline steps are done/active and
whether the run has reached the care-plan gate. This keeps the mock deterministic
and testable (inject a fake clock) with no background threads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
        run.pinned_status = m.RunStatus.cancelled
        return True

    def submit_review(self, run_id: str, action: m.ReviewAction) -> Run | None:
        """Returns the run if it was at the gate; None if not found; raises
        ValueError if the run is not currently awaiting review (→ 409)."""
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
        else:  # request_changes → regenerate; loop back to running
            run.previous_feedback = action
            run.review_iteration += 1
            run.effective_start = self._clock()
            run.pinned_status = None
        return run

    # -- progression --
    def _elapsed(self, run: Run) -> timedelta:
        return self._clock() - run.effective_start

    def _status(self, run: Run) -> m.RunStatus:
        if run.pinned_status is not None:
            return run.pinned_status
        if self._elapsed(run) >= AUTO_DURATION:
            return m.RunStatus.awaiting_careplan_review
        return m.RunStatus.running

    def _steps(self, run: Run) -> tuple[list[m.PipelineStep], list[m.StepKey]]:
        status = self._status(run)
        done = {m.RunStatus.completed, m.RunStatus.awaiting_careplan_review}
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
```

- [ ] **Step 2: Write the store tests**

Create `acp-writer/tests/test_bff_store.py`:

```python
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
```

- [ ] **Step 3: Run — expect FAIL (no `data.py` yet)**

Run: `pytest tests/test_bff_store.py -v`
Expected: FAIL with `ModuleNotFoundError`/`AttributeError` on `acp_writer.mocks.data` — resolved in Task 3.

- [ ] **Step 4: Commit the store (tests go green after Task 3)**

```bash
git add acp-writer/src/acp_writer/mocks/__init__.py acp-writer/src/acp_writer/mocks/store.py acp-writer/tests/test_bff_store.py
git commit -m "Add in-memory run store with clock-derived progression"
```

---

## Task 3: Canned clinical data

**Files:**
- Create: `acp-writer/src/acp_writer/mocks/data.py`

- [ ] **Step 1: Write the canned data + factories**

Create `acp-writer/src/acp_writer/mocks/data.py`:

```python
"""Canned clinical content for the mock BFF (hypertension exemplar).

`make_patient_summary` prefers a real name from an uploaded IPS bundle but falls
back to the exemplar, so uploads feel personalized without parsing full FHIR.
"""

from __future__ import annotations

from acp_writer.services import bff_models as m

_EXEMPLAR_PATIENT = m.PatientSummary(
    name="Jordan Rivera",
    birth_date="1957-03-12",
    gender="female",
    patient_reference="Patient/example-htn",
    conditions=[
        m.CodedItem(display="Essential hypertension", code="59621000", system="http://snomed.info/sct"),
        m.CodedItem(display="Type 2 diabetes mellitus", code="44054006", system="http://snomed.info/sct"),
    ],
    medications=[
        m.CodedItem(display="Metformin 500 mg", code="860975", system="http://www.nlm.nih.gov/research/umls/rxnorm"),
    ],
    allergies=[m.CodedItem(display="No known drug allergies", code="716186003", system="http://snomed.info/sct")],
    observations=[
        m.CodedItem(display="Systolic BP 152 mmHg", code="8480-6", system="http://loinc.org"),
        m.CodedItem(display="Diastolic BP 94 mmHg", code="8462-4", system="http://loinc.org"),
    ],
)

_CARE_PLAN = m.CarePlanView(
    goals=[
        m.PlanGoal(id="goal-1", description="Reduce blood pressure to < 130/80 mmHg within 3 months",
                   rationale="Stage 2 hypertension with diabetes comorbidity", source_cpg_id="AHA-HTN-2024"),
        m.PlanGoal(id="goal-2", description="Maintain HbA1c < 7.0%",
                   rationale="Diabetes co-management supports BP control", source_cpg_id="ADA-2024"),
    ],
    activities=[
        m.PlanActivity(id="act-1", goal_id="goal-1", description="Start lisinopril 10 mg daily",
                       detail="ACE inhibitor first-line for HTN + diabetes"),
        m.PlanActivity(id="act-2", goal_id="goal-1", description="DASH diet + sodium < 1500 mg/day",
                       detail="Lifestyle modification"),
        m.PlanActivity(id="act-3", goal_id="goal-2", description="Continue metformin 500 mg BID",
                       detail="No change"),
    ],
    conflicts=[
        m.PlanConflict(id="conf-1", severity="warning",
                       description="Monitor potassium: ACE inhibitor with existing renal risk"),
    ],
    fhir_bundle={
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "example-htn", "name": [{"text": "Jordan Rivera"}]}},
            {"resource": {"resourceType": "CarePlan", "id": "cp-example", "status": "draft",
                          "intent": "plan", "subject": {"reference": "Patient/example-htn"},
                          "description": "Hypertension management plan"}},
            {"resource": {"resourceType": "Goal", "id": "goal-1", "lifecycleStatus": "active",
                          "description": {"text": "Reduce blood pressure to < 130/80 mmHg"}}},
        ],
    },
)


def make_patient_summary(ips_bundle: dict) -> m.PatientSummary:
    """Return the exemplar patient, overriding the name from the IPS bundle if present."""
    patient = _EXEMPLAR_PATIENT.model_copy(deep=True)
    try:
        for entry in ips_bundle.get("entry", []):
            res = entry.get("resource", {})
            if res.get("resourceType") == "Patient":
                names = res.get("name") or []
                if names:
                    n = names[0]
                    patient.name = n.get("text") or " ".join(
                        [*n.get("given", []), n.get("family", "")]
                    ).strip() or patient.name
                ref_id = res.get("id")
                if ref_id:
                    patient.patient_reference = f"Patient/{ref_id}"
                break
    except AttributeError:
        pass
    return patient


def make_care_plan_view() -> m.CarePlanView:
    return _CARE_PLAN.model_copy(deep=True)
```

- [ ] **Step 2: Run the store tests — expect PASS**

Run: `pytest tests/test_bff_store.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add acp-writer/src/acp_writer/mocks/data.py
git commit -m "Add canned hypertension data + patient/careplan factories"
```

---

## Task 4: Mock router (the 8 endpoints)

**Files:**
- Create: `acp-writer/src/acp_writer/mocks/router.py`

The router wires HTTP to a `Store` instance held in `app.state` (so tests can inject a clock). It builds seed runs on construction.

- [ ] **Step 1: Write the router + seeding**

Create `acp-writer/src/acp_writer/mocks/router.py`:

```python
"""Mock API router implementing the PR #127 UI contract with canned data."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request

from acp_writer.mocks.store import AUTO_DURATION, Store
from acp_writer.services import bff_models as m


def seed(store: Store) -> None:
    """Populate a couple of runs so the dashboard is non-empty on first load."""
    now = store._clock()
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
    def list_runs(status: m.RunStatus | None = None, limit: int = 50):
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
    async def submit_review(run_id: str, action: m.ReviewAction):
        try:
            run = store.submit_review(run_id, action)
        except ValueError:
            raise HTTPException(status_code=409, detail="Run is not awaiting care-plan review")
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return store.to_detail(run)

    @router.get("/careplans", response_model=list[m.CarePlanSummary])
    def list_careplans():
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
```

*Note:* `list_careplans` returns `CarePlanDetail` objects where `CarePlanSummary` is expected; FastAPI's `response_model=list[CarePlanSummary]` filters extra fields, so summaries come out clean.

- [ ] **Step 2: (test lives in Task 5)** — the router is exercised via the app. Proceed.

- [ ] **Step 3: Commit**

```bash
git add acp-writer/src/acp_writer/mocks/router.py
git commit -m "Add mock BFF router implementing the 8 UI-contract endpoints"
```

---

## Task 5: FastAPI app + endpoint tests

**Files:**
- Create: `acp-writer/src/acp_writer/services/bff.py`
- Test: `acp-writer/tests/test_bff_api.py`

- [ ] **Step 1: Write the app**

Create `acp-writer/src/acp_writer/services/bff.py`:

```python
"""BFF for the acp-writer React UI.

When SONATAFLOW_URL is unset (the default), mounts the mock router backed by an
in-memory store — no SonataFlow/MinIO/LLM/DMN/FHIR needed. The SonataFlow-backed
branch is a stub for the real BFF (Jaideep).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from acp_writer.mocks.router import build_router, seed
from acp_writer.mocks.store import Store

SONATAFLOW_URL = os.getenv("SONATAFLOW_URL", "")
CORS_ORIGINS = os.getenv("BFF_CORS_ORIGINS", "http://localhost:3001").split(",")


def create_app() -> FastAPI:
    app = FastAPI(title="acp-writer-bff", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    mock_mode = not SONATAFLOW_URL
    store = Store()
    app.state.store = store
    app.state.mock_mode = mock_mode

    @app.get("/health")
    def health():
        return {"status": "UP", "service": "acp-writer-bff", "mock": mock_mode}

    if mock_mode:
        seed(store)
        app.include_router(build_router(store))
    else:  # pragma: no cover - real BFF is Jaideep's work (SonataFlow-backed)
        raise NotImplementedError(
            "SonataFlow-backed BFF not implemented in the mock. Unset SONATAFLOW_URL "
            "to run in mock mode."
        )

    return app


app = create_app()
```

- [ ] **Step 2: Write endpoint tests**

Create `acp-writer/tests/test_bff_api.py`:

```python
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
```

- [ ] **Step 3: Run endpoint tests — expect PASS**

Run: `pytest tests/test_bff_api.py -v`
Expected: all tests PASS.

- [ ] **Step 4: Add the paths-conformance test**

Append to `acp-writer/tests/test_bff_contract.py`:

```python
def test_app_routes_match_contract_paths():
    from acp_writer.services.bff import create_app
    spec = _spec()
    contract_paths = set(spec["paths"].keys())  # e.g. "/runs", "/runs/{runId}"
    app = create_app()
    app_paths = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/v1"):
            # normalize {run_id} → {runId}, strip prefix to match contract keys
            rel = path[len("/api/v1"):]
            rel = rel.replace("{run_id}", "{runId}").replace("{careplan_id}", "{careplanId}")
            app_paths.add(rel)
    assert app_paths == contract_paths, {
        "missing_in_app": sorted(contract_paths - app_paths),
        "extra_in_app": sorted(app_paths - contract_paths),
    }
```

- [ ] **Step 5: Run the full contract test — expect PASS**

Run: `pytest tests/test_bff_contract.py -v`
Expected: all PASS. (`create_app()` runs in mock mode since `SONATAFLOW_URL` is unset in the test env.)

- [ ] **Step 6: Run the whole suite (incl. architecture boundary tests)**

Run: `pytest tests/test_bff_store.py tests/test_bff_api.py tests/test_bff_contract.py tests/test_architecture.py -v`
Expected: all PASS. The architecture test confirms nothing new imports the benchmark package; our modules import only fastapi/pydantic/stdlib.

- [ ] **Step 7: Commit**

```bash
git add acp-writer/src/acp_writer/services/bff.py acp-writer/tests/test_bff_api.py acp-writer/tests/test_bff_contract.py
git commit -m "Add mock BFF FastAPI app + endpoint and path-conformance tests"
```

---

## Task 6: Local run + manual smoke

**Files:**
- Create: `acp-writer/src/acp_writer/mocks/README.md`

- [ ] **Step 1: Start the app locally**

Run (from `acp-writer/`): `uvicorn acp_writer.services.bff:app --port 8082 --reload`
Expected: uvicorn starts; `GET http://localhost:8082/health` returns `{"status":"UP",...,"mock":true}`.

- [ ] **Step 2: Smoke the review loop with curl**

```bash
curl -s localhost:8082/api/v1/runs | python -m json.tool          # seed rows incl. a gate run
RID=$(curl -s -XPOST localhost:8082/api/v1/runs -H 'content-type: application/json' -d '{"ipsBundle":{"resourceType":"Bundle"}}' | python -c 'import sys,json;print(json.load(sys.stdin)["runId"])')
sleep 15 && curl -s localhost:8082/api/v1/runs/$RID | python -m json.tool   # should be awaiting_careplan_review
curl -s -XPOST localhost:8082/api/v1/runs/$RID/review/careplan -H 'content-type: application/json' -d '{"decision":"approve"}' | python -m json.tool
curl -s localhost:8082/api/v1/careplans | python -m json.tool
```
Expected: the created run reaches `awaiting_careplan_review` (with `carePlan`), then `completed` after approve, and appears under `/careplans`.

- [ ] **Step 3: Write the README**

Create `acp-writer/src/acp_writer/mocks/README.md`:

```markdown
# acp-writer mock BFF

A canned-data implementation of the PR #127 UI contract
(`acp-writer/api/bff-openapi.yaml`) for developing/demoing the React UI without
the real pipeline (no SonataFlow/MinIO/LLM/DMN/FHIR).

## Run locally

    cd acp-writer
    pip install -e '.[test]'
    uvicorn acp_writer.services.bff:app --port 8082 --reload

The UI's `vite.config.ts` already proxies `/api` and `/health` to `localhost:8082`,
so `npm run dev` in `acp-writer/ui` talks to this mock.

## Behavior

- A created run advances one automated step every ~2s, reaching
  `awaiting_careplan_review` (~14s) with a full `CarePlanView`.
- `POST /runs/{id}/review/careplan` with `approve` completes the run and persists
  the plan to `/careplans`; `request_changes` loops back to `running` and returns
  with `reviewIteration`/`previousFeedback` on the next gate.
- Two seed runs (one completed, one pinned at the gate) make the dashboard non-empty.

## Mode

Mock mode is active whenever `SONATAFLOW_URL` is unset. The SonataFlow-backed
branch is the real BFF's responsibility.
```

- [ ] **Step 4: Commit**

```bash
git add acp-writer/src/acp_writer/mocks/README.md
git commit -m "Document local mock BFF usage"
```

---

## Task 7: Container image

**Files:**
- Create: `acp-writer/deploy/pods/Containerfile.bff`

- [ ] **Step 1: Write the Containerfile**

Create `acp-writer/deploy/pods/Containerfile.bff` (build context = repo root, mirroring `cpg-ingester/deploy/pods/Containerfile.bff`):

```dockerfile
FROM registry.access.redhat.com/ubi9/python-312:latest
USER 0
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic
COPY acp-writer/src/ /app/src/
ENV PYTHONPATH=/app/src
RUN chmod -R g=u /app
USER 1001
EXPOSE 8080
CMD ["uvicorn", "acp_writer.services.bff:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Build the image with podman**

Run (from repo root): `podman build -f acp-writer/deploy/pods/Containerfile.bff -t acp-writer-bff:dev .`
Expected: build succeeds.

- [ ] **Step 3: Run the container and smoke it**

```bash
podman run --rm -d -p 8082:8080 --name acp-bff acp-writer-bff:dev
sleep 2 && curl -s localhost:8082/health
curl -s localhost:8082/api/v1/status
podman stop acp-bff
```
Expected: `/health` returns `mock:true`; `/status` returns JSON. (Import hygiene holds — the image installs only fastapi/uvicorn/pydantic, proving no heavy deps are pulled.)

- [ ] **Step 4: Commit**

```bash
git add acp-writer/deploy/pods/Containerfile.bff
git commit -m "Add Containerfile for the acp-writer mock BFF pod"
```

---

## Task 8: Framework wiring (chart-pods)

**Files:**
- Modify: `acp-writer/deploy/chart-pods/values.yaml`
- Modify: `acp-writer/deploy/chart-pods/templates/deployments.yaml`

- [ ] **Step 1: Add the `bff` pod to values.yaml**

In `acp-writer/deploy/chart-pods/values.yaml`, under `pods:` (add after `fhir-server`, before `ui`):

```yaml
  bff:
    enabled: true
    sandboxed: false
    image: acp-writer-bff
    tag: latest
    port: 8080
    # No sonataflowUrl → the BFF runs in mock mode (canned data).
    resources:
      requests:
        cpu: 100m
        memory: 256Mi
      limits:
        cpu: 500m
        memory: 512Mi
```

- [ ] **Step 2: Add BFF env passthrough to deployments.yaml**

In `acp-writer/deploy/chart-pods/templates/deployments.yaml`, inside the `{{- if $pod.env }}` block (after the `decisionEngineUrl` block, before its closing `{{- end }}`), add so the same pod supports the real BFF later:

```yaml
            {{- if $pod.env.sonataflowUrl }}
            - name: SONATAFLOW_URL
              value: {{ $pod.env.sonataflowUrl | quote }}
            {{- end }}
            {{- if $pod.env.minioEndpoint }}
            - name: MINIO_ENDPOINT
              value: {{ $pod.env.minioEndpoint | quote }}
            {{- end }}
```

- [ ] **Step 3: Render the chart and verify the bff Deployment**

Run (from repo root):
```bash
helm template acp acp-writer/deploy/chart-pods --set image.namespace=test \
  | grep -A2 'name: acp-bff' ; \
helm template acp acp-writer/deploy/chart-pods --set image.namespace=test \
  | grep -c 'kind: Deployment'
```
Expected: a Deployment `acp-bff` renders (bff is `sandboxed: false`), and the Deployment count increased by one vs before. No `SONATAFLOW_URL` env appears for bff (mock mode).

- [ ] **Step 4: Lint**

Run: `helm lint acp-writer/deploy/chart-pods`
Expected: `1 chart(s) linted, 0 chart(s) failed`.

- [ ] **Step 5: Commit**

```bash
git add acp-writer/deploy/chart-pods/values.yaml acp-writer/deploy/chart-pods/templates/deployments.yaml
git commit -m "Wire mock BFF as the chart-pods bff pod (mock mode)"
```

---

## Task 9: Cluster milestone (manual verification)

This task validates the on-cluster deployment seam. It requires `oc login` and the image built into the namespace's registry. It is a milestone check, not automated.

**Dependency note:** a full browser round-trip (SPA served by nginx → `/api` → bff) also needs the React `ui` pod image, which is the *other session's* deliverable. Until then, verify the bff pod directly via port-forward.

- [ ] **Step 1: Build the bff image into the cluster**

The framework's `acp-writer/deploy/setup-images.sh` builds pod images from the `deploy/pods/Dockerfile.*` list. Confirm whether it globs `Containerfile.bff` or an explicit list; if explicit, add `bff → Containerfile.bff` following the existing entries. (Read `acp-writer/deploy/setup-images.sh` first.) Then run it per `deploy/README.md`, or do a one-off BuildConfig:

```bash
oc new-build --name acp-writer-bff --binary --strategy=docker \
  --to=acp-writer-bff:latest -n <namespace> 2>/dev/null || true
oc start-build acp-writer-bff --from-dir=. \
  --build-arg DOCKERFILE=acp-writer/deploy/pods/Containerfile.bff -F -n <namespace>
```
Expected: image `acp-writer-bff:latest` in the namespace ImageStream.

- [ ] **Step 2: Deploy just the bff pod**

```bash
helm upgrade --install acp acp-writer/deploy/chart-pods \
  --set image.namespace=<namespace> \
  --set pods.patient-data.enabled=false --set pods.llm-reasoning.enabled=false \
  --set pods.decision-engine.enabled=false --set pods.fhir-generation.enabled=false \
  --set pods.fhir-server.enabled=false --set pods.ui.enabled=false \
  -n <namespace>
oc rollout status deploy/acp-bff -n <namespace>
```
Expected: `acp-bff` Deployment becomes Available (no secrets, no other pods).

- [ ] **Step 3: Verify the contract on-cluster**

```bash
oc port-forward svc/acp-bff 8082:8080 -n <namespace> &
sleep 2
curl -s localhost:8082/health
curl -s localhost:8082/api/v1/runs | python -m json.tool
kill %1
```
Expected: `/health` `mock:true`; `/api/v1/runs` returns seed rows. The mock BFF serves the full contract on-cluster with zero backend dependencies.

- [ ] **Step 4: Record the result** in `dev_docs/design/2026-08-19-acp-writer-mock-bff-design.md` under a new "Cluster verification" note (date + outcome), and commit.

---

## Self-Review notes (already reconciled)

- **Spec coverage:** all 8 endpoints + `/health` (Tasks 4–5); run progression + review loop (Task 2); canned data incl. `CarePlanView` + FHIR bundle (Task 3); local run (Task 6); Containerfile (Task 7); chart-pods pod + env (Task 8); cluster milestone (Task 9); CORS scoped, no PHI persisted (Task 5); conformance harness (Tasks 1, 5); ownership stub for the real branch (Task 5).
- **Deferred to other owners (documented, not built here):** the React `ui` pod serving the SPA and its `API_URL`/`bffHost` nginx wiring (other session); the SonataFlow-backed BFF branch and workflow gate #129 (Jaideep); contract-comment hygiene for `StepKey.review_careplan` (contract PR).
- **Type consistency:** model field aliases are asserted equal to the contract schema properties by `test_bff_contract.py`, so drift fails the build.
