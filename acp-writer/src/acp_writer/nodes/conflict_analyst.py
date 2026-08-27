"""Conflict Analyst — plan-level conflict detection.

Runs once after the brief-review loop converges and before FHIR generation.
Inspects the composed PlanningBrief (goals + activities from multiple CPGs) and
flags conflicts (overlap / contradiction / divergent target / divergent
schedule) for the reviewing clinician. It annotates the brief; it NEVER changes
goals or activities.

Detection is a generic LLM judgment task — no DMN, no clinical knowledge base.
See working/issue-169-conflict-surfacing/dev-plan.md §WS2.
"""

import json
import logging
import time

import mlflow
from cpg_contracts import content_to_text, get_llm

from acp_writer.output import write_artifact
from acp_writer.planning_brief import (
    ConflictCategory,
    ConflictEntry,
    ConflictSeverity,
    ConflictSource,
    ConflictStatus,
    _coerce_enum,
    coerce_conflicts,
    conflict_id,
)
from acp_writer.prompts.conflict_analyst import (
    CONFLICT_ANALYST_SYSTEM,
    CONFLICT_ANALYST_USER,
)
from acp_writer.state import CarePlanComposerState

logger = logging.getLogger(__name__)


def _format_goals(goals: list[dict]) -> str:
    if not goals:
        return "None."
    lines = []
    for i, g in enumerate(goals):
        measure = g.get("target_measure_code") or {}
        measure_str = measure.get("display") or measure.get("code") or "—"
        target = g.get("target_value") or {}
        target_str = ""
        if target:
            lo, hi, unit = target.get("low"), target.get("high"), target.get("unit", "")
            target_str = f" target={lo or ''}-{hi or ''} {unit}".rstrip()
        lines.append(
            f"[{i}] {g.get('description', '')} "
            f"(measure={measure_str}{target_str}; "
            f"cpg={g.get('source_cpg')}; rec={g.get('source_recommendation_id')})"
        )
    return "\n".join(lines)


def _format_activities(activities: list[dict]) -> str:
    if not activities:
        return "None."
    lines = []
    for i, a in enumerate(activities):
        dose_bits = " ".join(
            str(x) for x in (a.get("dose"), a.get("route"), a.get("frequency")) if x
        )
        dose_str = f"; dose={dose_bits}" if dose_bits else ""
        lines.append(
            f"[{i}] ({a.get('type')}) {a.get('description', '')}{dose_str} "
            f"(cpg={a.get('source_cpg')}; rec={a.get('source_recommendation_id')})"
        )
    return "\n".join(lines)


def _format_recommendations(recommendations: list[dict]) -> str:
    if not recommendations:
        return "None."
    by_cpg: dict[str, list[dict]] = {}
    for rec in recommendations:
        by_cpg.setdefault(rec.get("source_cpg") or "unspecified", []).append(rec)
    blocks = []
    for cpg, recs in by_cpg.items():
        lines = [f"### {cpg}"]
        for rec in recs:
            lines.append(
                f"- {rec.get('id')}: {rec.get('title')} — {rec.get('content')}"
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _format_medications(medication_codes: list[dict]) -> str:
    if not medication_codes:
        return "None recorded."
    return ", ".join(
        m.get("display", m.get("code", "unknown")) for m in medication_codes
    )


def _content_key(
    category: str,
    goal_indices: list[int],
    activity_indices: list[int],
    goals: list[dict],
    activities: list[dict],
) -> str:
    """Derive the semantic content-key that stabilizes a conflict id across
    regenerations AND keeps distinct same-category conflicts from colliding
    (see planning_brief.conflict_id). Built for EVERY category from the
    referenced goals' measures and activities' codes/descriptions — two
    overlap conflicts on different diet activities get different keys, so their
    ids differ. Fully bounds-checked and str-coerced (never raises)."""
    tokens: list[str] = []
    for i in goal_indices:
        if 0 <= i < len(goals):
            g = goals[i]
            measure = g.get("target_measure_code") or {}
            tokens.append(
                str(measure.get("code") or measure.get("display") or g.get("description") or "")
            )
    for i in activity_indices:
        if 0 <= i < len(activities):
            a = activities[i]
            code = a.get("code") or {}
            display = code.get("display")
            if not display:
                display = " ".join(str(a.get("description") or "").split()[:4])
            tokens.append(str(display))
    return "|".join(sorted({t.lower() for t in tokens if t}))


def _uniquify_ids(entries: list[ConflictEntry]) -> None:
    """Deterministically suffix colliding conflict ids (``-2``, ``-3``, …).

    Semantic ids (:func:`conflict_id`) can still collide for same-category
    conflicts whose sources and content-keys coincide; downstream Provenance
    and read-back key on the id, so duplicates would clobber each other.
    Assignment is order-independent (sort by base id then description) so a
    regeneration assigns the same suffixes. Mutates ``entries`` in place."""
    seen: dict[str, int] = {}
    for idx in sorted(range(len(entries)), key=lambda i: (entries[i].id, entries[i].description)):
        base = entries[idx].id
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            entries[idx].id = f"{base}-{seen[base]}"


def _build_entry(
    raw: dict, goals: list[dict], activities: list[dict]
) -> ConflictEntry | None:
    """Validate one raw LLM conflict into a ConflictEntry, clamping indices.
    Returns None when the item is not an object or all referenced indices are
    out of range. Defensive against malformed items — every field access is
    guarded/coerced so a single bad conflict can't crash the advisory step."""
    if not isinstance(raw, dict):
        logger.warning("Dropping non-object conflict item: %r", raw)
        return None

    goal_indices = [
        i for i in (raw.get("goal_indices") or []) if isinstance(i, int) and 0 <= i < len(goals)
    ]
    activity_indices = [
        i for i in (raw.get("activity_indices") or []) if isinstance(i, int) and 0 <= i < len(activities)
    ]
    if not goal_indices and not activity_indices:
        logger.warning("Dropping conflict with no valid indices: %s", raw.get("description"))
        return None

    sources: list[ConflictSource] = []
    for s in (raw.get("sources") or []):
        if not isinstance(s, dict) or not s.get("cpg_id"):
            continue
        try:
            sources.append(
                ConflictSource(
                    cpg_id=str(s.get("cpg_id")),
                    recommendation_id=(str(s["recommendation_id"]) if s.get("recommendation_id") else None),
                    excerpt=(str(s["excerpt"]) if s.get("excerpt") else None),
                )
            )
        except Exception as exc:  # noqa: BLE001 — drop the bad source, keep the conflict
            logger.warning("Dropping malformed conflict source %r: %s", s, exc)

    category = _coerce_enum(raw.get("category"), ConflictCategory, ConflictCategory.OTHER)
    severity = _coerce_enum(raw.get("severity"), ConflictSeverity, ConflictSeverity.WARNING)
    content_key = _content_key(category.value, goal_indices, activity_indices, goals, activities)

    return ConflictEntry(
        id=conflict_id(category, sources, content_key),
        category=category,
        severity=severity,
        status=ConflictStatus.DETECTED,
        description=str(raw.get("description") or ""),
        rationale=(str(raw["rationale"]) if raw.get("rationale") else None),
        suggested_resolution=(str(raw["suggested_resolution"]) if raw.get("suggested_resolution") else None),
        confidence=(str(raw["confidence"]) if raw.get("confidence") else None),
        goal_indices=goal_indices,
        activity_indices=activity_indices,
        sources=sources,
        detected_by="llm",
    )


def _parse_conflicts(content: str) -> list[dict]:
    """Extract the conflicts list from an LLM response, tolerating markdown
    fences. Raises on malformed JSON / wrong shape (drives the one retry)."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1 : len(lines) - 1] if lines[-1].strip() == "```" else lines[1:])
    data = json.loads(text)
    if not isinstance(data, dict) or "conflicts" not in data:
        raise ValueError("response missing 'conflicts' key")
    conflicts = data["conflicts"]
    if not isinstance(conflicts, list):
        raise ValueError("'conflicts' is not a list")
    if not all(isinstance(c, dict) for c in conflicts):
        # Shape junk (e.g. a list of bare strings) — raise so the one retry can
        # coax a well-formed response before we fall back to graceful degradation.
        raise ValueError("each conflict must be a JSON object")
    return conflicts


def _carry_forward(fresh: list[ConflictEntry], prior: list[dict]) -> None:
    """Copy clinician-set status/resolution from prior conflicts onto freshly
    detected ones with a matching (semantic) id. Mutates ``fresh`` in place."""
    prior_by_id = {c.get("id"): c for c in prior if c.get("id")}
    for entry in fresh:
        p = prior_by_id.get(entry.id)
        if p and p.get("status") in (ConflictStatus.ACKNOWLEDGED.value, ConflictStatus.RESOLVED.value):
            entry.status = ConflictStatus(p["status"])
            entry.resolution = p.get("resolution")


def _merge_composer(fresh: list[ConflictEntry], prior: list[dict]) -> list[ConflictEntry]:
    """Keep legacy composer-detected conflicts unless a fresh analyst conflict
    supersedes them (same category with intersecting affected indices)."""
    kept: list[ConflictEntry] = []
    for c in prior:
        if c.get("detected_by") != "composer":
            continue
        c_ai, c_gi = set(c.get("activity_indices") or []), set(c.get("goal_indices") or [])
        superseded = any(
            e.category.value == c.get("category")
            and (set(e.activity_indices) & c_ai or set(e.goal_indices) & c_gi)
            for e in fresh
        )
        if not superseded:
            try:
                kept.append(ConflictEntry.model_validate(c))
            except Exception as exc:  # noqa: BLE001 — defensive; never fail the run on legacy data
                logger.warning("Skipping un-coercible composer conflict: %s", exc)
    return kept


@mlflow.trace(name="conflict_analyst")
def conflict_analyst(state: CarePlanComposerState) -> dict:
    """Detect plan-level conflicts and annotate the planning brief."""
    brief = dict(state.get("planning_brief") or {})
    goals = brief.get("goals") or []
    activities = brief.get("activities") or []
    output_dir = state.get("output_dir", "")

    if not goals and not activities:
        logger.info("Conflict analysis: empty plan — nothing to analyze")
        return {"planning_brief": brief}

    prior = coerce_conflicts(brief.get("conflicts"))

    user_prompt = CONFLICT_ANALYST_USER.format(
        goals=_format_goals(goals),
        activities=_format_activities(activities),
        recommendations=_format_recommendations(state.get("recommendations") or []),
        conditions=", ".join(
            c.get("display", c.get("code", "?")) for c in (state.get("condition_codes") or [])
        )
        or "None recorded.",
        medications=_format_medications(state.get("medication_codes") or []),
    )
    rendered_prompt = f"{CONFLICT_ANALYST_SYSTEM}\n\n{user_prompt}"

    logger.info("── Conflict Analyst ──")
    llm = get_llm(state)
    messages = [
        {"role": "system", "content": CONFLICT_ANALYST_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]

    raw_conflicts: list[dict] | None = None
    last_response_text = ""
    for attempt in range(2):
        try:
            t0 = time.time()
            response = llm.invoke(messages)
            logger.info("LLM responded in %.1fs", time.time() - t0)
            last_response_text = content_to_text(response.content)
            raw_conflicts = _parse_conflicts(last_response_text)
            break
        except Exception as e:  # noqa: BLE001 — parse/transport errors both retried once
            if attempt == 0:
                if last_response_text:
                    # A response arrived but didn't parse — echo it back with a
                    # correction so the model can fix its own output.
                    logger.warning("Conflict parse failed (attempt 1), retrying with feedback: %s", e)
                    messages.append({"role": "assistant", "content": last_response_text})
                    messages.append({
                        "role": "user",
                        "content": f"That response could not be parsed ({e}). "
                        "Return ONLY the JSON object with a top-level 'conflicts' list.",
                    })
                else:
                    # Transport/empty error before any text — retry with the
                    # ORIGINAL messages. Never append an empty assistant turn:
                    # some providers reject empty-content messages outright.
                    logger.warning("Conflict LLM call failed with no response (attempt 1), retrying: %s", e)
                continue
            # Graceful degradation: keep the brief's existing conflicts, continue.
            logger.error("Conflict analysis failed after retry — keeping existing conflicts: %s", e)
            return {"planning_brief": brief, "conflict_prompt": rendered_prompt}

    fresh: list[ConflictEntry] = []
    malformed = 0
    for r in (raw_conflicts or []):
        try:
            entry = _build_entry(r, goals, activities)
        except Exception as exc:  # noqa: BLE001 — advisory step must never crash the run
            logger.warning("Skipping malformed conflict item (%s): %r", exc, r)
            malformed += 1
            continue
        if entry is not None:
            fresh.append(entry)
    if malformed:
        logger.info("Conflict analysis: skipped %d malformed conflict item(s)", malformed)

    _carry_forward(fresh, prior)
    merged = fresh + _merge_composer(fresh, prior)
    _uniquify_ids(merged)

    brief["conflicts"] = [e.model_dump(mode="json") for e in merged]

    if output_dir:
        write_artifact(output_dir, "conflict-analysis.json", {"conflicts": brief["conflicts"]})

    counts = {cat: 0 for cat in (c.value for c in ConflictCategory)}
    for e in merged:
        counts[e.category.value] += 1
    logger.info(
        "Conflict analysis: %d conflicts (%d overlap, %d contradiction, "
        "%d divergent_target, %d divergent_schedule, %d other)",
        len(merged),
        counts["overlap"],
        counts["contradiction"],
        counts["divergent_target"],
        counts["divergent_schedule"],
        counts["other"],
    )

    return {"planning_brief": brief, "conflict_prompt": rendered_prompt}
