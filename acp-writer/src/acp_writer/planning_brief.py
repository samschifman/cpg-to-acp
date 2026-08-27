"""Planning Brief — formal contract between LLM reasoning and FHIR generation.

Internal to acp-writer (not in shared/cpg_contracts). Carries extra
workflow context (actors, escalation, sequencing) for future BPMN.
"""

import hashlib
from datetime import datetime
from enum import Enum
from typing import Any

import mlflow
from pydantic import BaseModel, Field, model_validator


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
    conflict_analyst node."""

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
    # resolution: kept for the #172 per-conflict resolution-recording flow, where
    # a clinician's instruction will be recorded on the conflict Provenance.
    resolution: str | None = None  # clinician's instruction once resolved
    suggested_resolution: str | None = None  # analyst's conservative suggestion for the reviewing clinician (advisory only — never auto-applied)


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


_SEVERITY_SYNONYMS = {
    "critical": ConflictSeverity.CRITICAL,
    "high": ConflictSeverity.CRITICAL,
    "severe": ConflictSeverity.CRITICAL,
    "warning": ConflictSeverity.WARNING,
    "warn": ConflictSeverity.WARNING,
    "medium": ConflictSeverity.WARNING,
    "moderate": ConflictSeverity.WARNING,
    "info": ConflictSeverity.INFO,
    "informational": ConflictSeverity.INFO,
    "low": ConflictSeverity.INFO,
    "minor": ConflictSeverity.INFO,
}


def _coerce_enum(value, enum_cls, default):
    """Coerce a raw value into a member of ``enum_cls``, falling back to
    ``default`` when it can't. Shared by :func:`coerce_conflicts` and the
    conflict_analyst node so both paths normalize enums identically."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return default


def _coerce_severity(value) -> ConflictSeverity:
    """Coerce a severity, mapping common synonyms (``high`` → ``critical``,
    ``low`` → ``info``, …). Unknown values default to ``warning``."""
    if isinstance(value, ConflictSeverity):
        return value
    if isinstance(value, str):
        mapped = _SEVERITY_SYNONYMS.get(value.strip().lower())
        if mapped is not None:
            return mapped
    return ConflictSeverity.WARNING


def _norm_source(s) -> dict | None:
    """Normalize one raw conflict source into a ConflictSource-ready dict, or
    ``None`` if no CPG id can be recovered. Accepts bare strings and both
    snake_case and camelCase keys, and str-coerces field values."""
    if isinstance(s, str):
        return {"cpg_id": s} if s.strip() else None
    if isinstance(s, dict):
        cpg = s.get("cpg_id", s.get("cpgId"))
        if cpg is None or not str(cpg).strip():
            return None
        out: dict = {"cpg_id": str(cpg)}
        rec = s.get("recommendation_id", s.get("recommendationId"))
        if rec is not None and str(rec).strip():
            out["recommendation_id"] = str(rec)
        excerpt = s.get("excerpt")
        if excerpt is not None and str(excerpt).strip():
            out["excerpt"] = str(excerpt)
        return out
    return None


@mlflow.trace(name="coerce_conflicts")
def coerce_conflicts(raw: list | None) -> list[dict]:
    """Upgrade legacy / loosely-shaped conflict entries into new-shape dicts.

    Total by construction — never raises. Handles: bare strings
    (→ description-only), ``sources: list[str]`` and camelCase source keys
    (→ normalized ConflictSource dicts), the legacy ``recommendation_ids`` key,
    ConflictEntry/BaseModel instances (via ``model_dump``), enum synonyms
    (severity ``high`` → ``critical`` etc., unknown categories → ``other``),
    and missing ids (computed via :func:`conflict_id`). Un-recoverable sources
    are dropped individually rather than sinking the whole conflict. Returns
    dicts ready to validate through :class:`ConflictEntry`.
    """
    if not raw:
        return []
    cleaned: list[dict] = []
    for item in raw:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if isinstance(item, str):
            entry: dict = {
                "description": item,
                "sources": [],
                "goal_indices": [],
                "activity_indices": [],
            }
        elif isinstance(item, dict):
            entry = dict(item)
            legacy_sources = entry.get("sources")
            if legacy_sources is None:
                legacy_sources = entry.get("recommendation_ids", [])
            norm_sources: list[dict] = []
            for s in legacy_sources or []:
                ns = _norm_source(s)
                if ns is not None:
                    norm_sources.append(ns)
            entry["sources"] = norm_sources
            entry.pop("recommendation_ids", None)
            entry.setdefault("goal_indices", [])
            entry.setdefault("activity_indices", [])
            entry["description"] = str(entry.get("description") or "")
            if "category" in entry:
                entry["category"] = _coerce_enum(
                    entry.get("category"), ConflictCategory, ConflictCategory.OTHER
                ).value
            if "severity" in entry:
                entry["severity"] = _coerce_severity(entry.get("severity")).value
            if "status" in entry:
                entry["status"] = _coerce_enum(
                    entry.get("status"), ConflictStatus, ConflictStatus.DETECTED
                ).value
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


def render_conflicts_feedback(conflicts: list | None) -> str:
    """Render previously-detected conflicts into a compact composer-feedback block.

    On a request-changes recomposition the clinician's comment may reference the
    flagged conflicts ("resolve all identified conflicts as you suggested") — but
    the composer only sees the comment, never the conflicts themselves. This
    renders the prior brief's conflicts into a "## Previously identified
    conflicts" block that is fed alongside the comment so the LLM has a referent
    for both halves. Each entry lists id, category, severity, description,
    analyst rationale, suggested resolution, and the implicated CPG/rec ids.

    Compact by construction (no raw JSON). Returns "" when there is nothing to
    render so callers can concatenate unconditionally. Lives here (next to
    :func:`coerce_conflicts`) rather than in the split-path service so the
    monolith can reuse it when it grows a care-plan review loop (see issue #174).
    """
    conflicts = coerce_conflicts(conflicts)
    if not conflicts:
        return ""
    lines = [
        "## Previously identified conflicts",
        "The prior plan carried the plan-level conflicts below. Revise the plan "
        "to resolve them where clinically appropriate — a genuinely resolved "
        "conflict simply won't recur in the regenerated plan. These are advisory: "
        "do NOT force a change that is not clinically sound.",
        "",
    ]
    for c in conflicts:
        header = f"- [{c.get('id', '')}] {c.get('category', 'other')}"
        severity = c.get("severity")
        if severity:
            header += f" ({severity})"
        header += f": {c.get('description', '')}".rstrip()
        lines.append(header)
        rationale = c.get("rationale")
        if rationale:
            lines.append(f"  Rationale: {rationale}")
        suggestion = c.get("suggested_resolution")
        if suggestion:
            lines.append(f"  Suggested: {suggestion}")
        src_tokens = []
        for s in c.get("sources") or []:
            if not isinstance(s, dict) or not s.get("cpg_id"):
                continue
            token = str(s["cpg_id"])
            if s.get("recommendation_id"):
                token += f"/{s['recommendation_id']}"
            src_tokens.append(token)
        if src_tokens:
            lines.append(f"  Sources: {', '.join(src_tokens)}")
    return "\n".join(lines)


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

    @model_validator(mode="before")
    @classmethod
    def _coerce_conflicts_field(cls, data):
        """Make every PlanningBrief validation site tolerant of legacy/loose
        conflict shapes. Without this, one malformed conflict (a bare string, a
        ``high`` severity, a source missing its cpg_id) would raise mid-validate
        and callers that swallow the error would silently drop the ENTIRE brief
        — goals, activities and all. Runs :func:`coerce_conflicts` before field
        validation so the loss can never happen. Idempotent on clean input."""
        if isinstance(data, dict) and isinstance(data.get("conflicts"), list) and data["conflicts"]:
            data = dict(data)
            data["conflicts"] = coerce_conflicts(data["conflicts"])
        return data
