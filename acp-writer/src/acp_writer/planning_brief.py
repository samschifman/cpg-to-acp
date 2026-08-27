"""Planning Brief — formal contract between LLM reasoning and FHIR generation.

Internal to acp-writer (not in shared/cpg_contracts). Carries extra
workflow context (actors, escalation, sequencing) for future BPMN.
"""

import hashlib
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


class ConflictSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ConflictCategory(str, Enum):
    OVERLAP = "overlap"
    CONTRADICTION = "contradiction"
    DIVERGENT_TARGET = "divergent_target"
    DIVERGENT_SCHEDULE = "divergent_schedule"
    OTHER = "other"


class ConflictStatus(str, Enum):
    DETECTED = "detected"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class ConflictSource(BaseModel):
    """A guideline source implicated in a conflict."""

    cpg_id: str
    recommendation_id: str | None = None
    excerpt: str | None = None  # short quote from the source rec, for display


class ConflictEntry(BaseModel):
    """A plan-level conflict between goals/activities, detected by the
    conflict_analyst node (or, legacy, the composer)."""

    id: str  # stable, semantic — see conflict_id()
    category: ConflictCategory = ConflictCategory.OTHER
    severity: ConflictSeverity = ConflictSeverity.WARNING
    status: ConflictStatus = ConflictStatus.DETECTED
    description: str  # clinician-legible, names both items + guidelines
    rationale: str | None = None  # analyst reasoning (verbose OK — lands in Provenance note)
    confidence: str | None = None  # "low" | "medium" | "high"
    goal_indices: list[int] = Field(default_factory=list)
    activity_indices: list[int] = Field(default_factory=list)
    sources: list[ConflictSource] = Field(default_factory=list)
    resolution: str | None = None  # clinician's instruction once resolved
    detected_by: str = "llm"  # "llm" | "composer"


def conflict_id(
    category: ConflictCategory | str,
    sources: list[ConflictSource],
    content_key: str = "",
) -> str:
    """Compute a stable, *semantic* id for a conflict.

    Deliberately excludes goal/activity indices: a request-changes
    regeneration re-runs the composer LLM, which reorders/adds/drops items,
    so index-derived ids would break clinician status/resolution carry-over
    across regenerations. Instead the id is derived from the category, the
    implicated recommendation ids (falling back to CPG ids), and an optional
    ``content_key`` (e.g. the goal measure code for divergent targets, or the
    drug-name token for a drug contradiction). Order-insensitive.
    """
    cat = category.value if isinstance(category, ConflictCategory) else str(category)
    rec_ids = sorted({s.recommendation_id for s in sources if s.recommendation_id})
    if not rec_ids:
        rec_ids = sorted({s.cpg_id for s in sources if s.cpg_id})
    raw = f"{cat}|{','.join(rec_ids)}|{content_key}"
    return "conf-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def coerce_conflicts(raw: list | None) -> list[dict]:
    """Upgrade legacy / loosely-shaped conflict entries into new-shape dicts.

    Handles: bare strings (→ description-only), ``sources: list[str]``
    (→ ``[ConflictSource(cpg_id=...)]``), the legacy ``recommendation_ids``
    key, and missing ids (computed via :func:`conflict_id`). Entries with no
    explicit ``detected_by`` are treated as composer output. Returns dicts
    ready to validate through :class:`ConflictEntry`.
    """
    if not raw:
        return []
    cleaned: list[dict] = []
    for item in raw:
        if isinstance(item, str):
            entry: dict = {
                "description": item,
                "sources": [],
                "goal_indices": [],
                "activity_indices": [],
                "detected_by": "composer",
            }
        elif isinstance(item, dict):
            entry = dict(item)
            legacy_sources = entry.get("sources")
            if legacy_sources is None:
                legacy_sources = entry.get("recommendation_ids", [])
            norm_sources: list[dict] = []
            for s in legacy_sources or []:
                if isinstance(s, str):
                    norm_sources.append({"cpg_id": s})
                elif isinstance(s, dict):
                    norm_sources.append(s)
            entry["sources"] = norm_sources
            entry.pop("recommendation_ids", None)
            entry.setdefault("goal_indices", [])
            entry.setdefault("activity_indices", [])
            entry.setdefault("description", "")
            entry.setdefault("detected_by", "composer")
        else:
            continue
        if not entry.get("id"):
            sources = [ConflictSource(**s) for s in entry["sources"]]
            entry["id"] = conflict_id(
                entry.get("category", ConflictCategory.OTHER),
                sources,
            )
        cleaned.append(entry)
    return cleaned


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
