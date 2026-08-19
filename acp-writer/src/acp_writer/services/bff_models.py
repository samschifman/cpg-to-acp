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
