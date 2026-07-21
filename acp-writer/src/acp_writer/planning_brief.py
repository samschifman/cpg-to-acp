"""Planning Brief — formal contract between LLM reasoning and FHIR generation.

Internal to acp-writer (not in shared/cpg_contracts). Carries extra
workflow context (actors, escalation, sequencing) for future BPMN.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FHIRCode(BaseModel):
    """A verified FHIR code with system URI."""

    system: str
    code: str
    display: str | None = None


class TargetValue(BaseModel):
    """A goal target value range with unit."""

    high: float | None = None
    low: float | None = None
    unit: str


class DMNAuditEntry(BaseModel):
    """Record of a single DMN model evaluation."""

    model_id: str
    model_name: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    fhir_references: list[str] = Field(
        default_factory=list,
        description="FHIR resource references used as input sources",
    )
    timestamp: datetime


class ActivityType(str, Enum):
    MEDICATION = "medication"
    MONITORING = "monitoring"
    LIFESTYLE = "lifestyle"
    REFERRAL = "referral"
    EDUCATIONAL = "educational"
    PROCESS = "process"


class ActivityWorkflow(BaseModel):
    """Workflow context for future BPMN generation.

    Captures actor assignments, sequencing, escalation paths,
    and monitoring triggers that FHIR CarePlan cannot represent.
    """

    actor: str | None = None
    sequence_after: str | None = Field(
        default=None,
        description="Activity description this must follow",
    )
    escalation: str | None = None
    monitoring_trigger: str | None = None


class PlanGoal(BaseModel):
    """A care plan goal with measurable target."""

    description: str
    target_measure_code: FHIRCode | None = None
    target_value: TargetValue | None = None
    source_recommendation_id: str | None = None
    source_cpg: str


class PlanActivity(BaseModel):
    """A care plan activity with type-specific fields and provenance."""

    type: ActivityType
    description: str

    code: FHIRCode | None = None
    dose: str | None = None
    route: str | None = None
    frequency: str | None = None
    specialty: str | None = None

    source_recommendation_id: str | None = None
    source_cpg: str
    source_dmn_call: int | None = Field(
        default=None,
        description="Index into dmn_audit_trail",
    )
    clinical_rationale: str | None = None
    workflow: ActivityWorkflow | None = None


class ConflictEntry(BaseModel):
    """A detected conflict between recommendations (placeholder)."""

    description: str
    activity_indices: list[int] = Field(
        description="Indices into the activities list",
    )
    sources: list[str] = Field(
        description="Source CPG IDs or recommendation IDs",
    )
    resolution: str | None = None


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REVISED = "revised"
    FLAGGED = "flagged"


class PlanningBrief(BaseModel):
    """The formal contract between Phase 1 (clinical reasoning) and
    Phase 2 (deterministic FHIR generation)."""

    patient_reference: str
    applicable_cpgs: list[str]
    dmn_audit_trail: list[DMNAuditEntry] = Field(default_factory=list)
    goals: list[PlanGoal]
    activities: list[PlanActivity]
    conflicts: list[ConflictEntry] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.PENDING
    review_feedback: str | None = None
