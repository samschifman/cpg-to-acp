"""Deterministic recommendation schema validation — Pydantic, cross-refs, enums, grading."""

import logging

from pydantic import ValidationError

from cpg_contracts import (
    CertaintyGrade,
    GradingSystem,
    Recommendation,
    SourceLocation,
)

logger = logging.getLogger(__name__)

VALID_REC_TYPES = {
    "treatment", "diagnostic", "monitoring", "lifestyle", "educational",
    "referral", "screening", "contraindication", "process",
}
VALID_STRENGTHS = {
    "strong-for", "conditional-for", "consensus", "no-recommendation",
    "conditional-against", "strong-against",
}
VALID_EVIDENCE = {"high", "moderate", "low", "very-low", "ungraded"}
VALID_PROVENANCE = {"reviewed", "new-added", "amended", "not-changed", "removed"}


def validate_recommendation(rec: dict, manifest_ids: set[str], declared_grading: str | None = None, max_page: int | None = None) -> list[str]:
    """Validate a single recommendation dict. Returns list of error messages."""
    errors = []
    rec_id = rec.get("id", "unknown")
    title = rec.get("title", "unknown")
    label = f"Rec '{title}' ({rec_id[:8]})"

    # 1. Pydantic validation
    try:
        clean = dict(rec)
        if clean.get("source_cpg") == "TBD":
            clean["source_cpg"] = "placeholder"
        Recommendation(**clean)
    except ValidationError as e:
        for err in e.errors():
            field = ".".join(str(l) for l in err["loc"])
            errors.append(f"{label}: Pydantic error on '{field}': {err['msg']}")
        return errors

    # 2. Recommendation type
    rec_type = rec.get("recommendation_type")
    if rec_type and rec_type not in VALID_REC_TYPES:
        errors.append(f"{label}: invalid recommendation_type '{rec_type}'")

    # 3. Certainty fields
    certainty = rec.get("certainty")
    if certainty and isinstance(certainty, dict):
        strength = certainty.get("strength")
        if strength and strength not in VALID_STRENGTHS:
            errors.append(f"{label}: invalid certainty.strength '{strength}'")

        evidence = certainty.get("evidence_quality")
        if evidence and evidence not in VALID_EVIDENCE:
            errors.append(f"{label}: invalid certainty.evidence_quality '{evidence}'")

        grading = certainty.get("grading_system")
        if grading:
            try:
                GradingSystem(grading)
            except ValueError:
                errors.append(f"{label}: invalid certainty.grading_system '{grading}'")

        if declared_grading and grading and grading != declared_grading:
            errors.append(
                f"{label}: certainty.grading_system '{grading}' doesn't match "
                f"CPG declared system '{declared_grading}'"
            )

    # 4. Provenance
    provenance = rec.get("provenance")
    if provenance and provenance not in VALID_PROVENANCE:
        errors.append(f"{label}: invalid provenance '{provenance}'")

    # 5. Cross-reference resolution
    cross_refs = rec.get("cross_references", []) or []
    for ref in cross_refs:
        if isinstance(ref, dict):
            target = ref.get("target_id", "")
        else:
            target = ref
        if target and target not in manifest_ids:
            errors.append(f"{label}: cross_reference target '{target[:8]}...' not in manifest")

    # 6. GUID in manifest
    if manifest_ids and rec_id not in manifest_ids:
        errors.append(f"{label}: id '{rec_id[:8]}...' not in manifest (pre-assigned GUIDs)")

    # 7. Source location page range
    source_loc = rec.get("source_location")
    if source_loc and isinstance(source_loc, dict):
        page_start = source_loc.get("page_start")
        if max_page and page_start and page_start > max_page:
            errors.append(f"{label}: source_location.page_start ({page_start}) exceeds document page count ({max_page})")

    return errors


def validate_recommendations(recs: list[dict], manifest_ids: set[str], declared_grading: str | None = None, max_page: int | None = None) -> list[str]:
    """Validate a batch of recommendations. Returns all errors."""
    all_errors = []
    for rec in recs:
        all_errors.extend(validate_recommendation(rec, manifest_ids, declared_grading, max_page))
    return all_errors
