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
    regenerations (see planning_brief.conflict_id)."""
    tokens: list[str] = []
    if category == ConflictCategory.DIVERGENT_TARGET.value:
        for i in goal_indices:
            measure = (goals[i].get("target_measure_code") or {}) if i < len(goals) else {}
            tokens.append(
                (measure.get("code") or measure.get("display") or goals[i].get("description", "")).lower()
                if i < len(goals) else ""
            )
    elif category == ConflictCategory.CONTRADICTION.value:
        for i in activity_indices:
            if i < len(activities):
                code = activities[i].get("code") or {}
                token = code.get("display") or activities[i].get("description", "").split()[:2]
                tokens.append(
                    (token if isinstance(token, str) else " ".join(token)).lower()
                )
    return "|".join(sorted({t for t in tokens if t}))


def _coerce_enum(value, enum_cls, default):
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return default


def _build_entry(
    raw: dict, goals: list[dict], activities: list[dict]
) -> ConflictEntry | None:
    """Validate one raw LLM conflict into a ConflictEntry, clamping indices.
    Returns None when all referenced indices are out of range."""
    goal_indices = [
        i for i in (raw.get("goal_indices") or []) if isinstance(i, int) and 0 <= i < len(goals)
    ]
    activity_indices = [
        i for i in (raw.get("activity_indices") or []) if isinstance(i, int) and 0 <= i < len(activities)
    ]
    if not goal_indices and not activity_indices:
        logger.warning("Dropping conflict with no valid indices: %s", raw.get("description"))
        return None

    sources = [
        ConflictSource(**s) for s in (raw.get("sources") or []) if isinstance(s, dict) and s.get("cpg_id")
    ]
    category = _coerce_enum(raw.get("category"), ConflictCategory, ConflictCategory.OTHER)
    severity = _coerce_enum(raw.get("severity"), ConflictSeverity, ConflictSeverity.WARNING)
    content_key = _content_key(category.value, goal_indices, activity_indices, goals, activities)

    return ConflictEntry(
        id=conflict_id(category, sources, content_key),
        category=category,
        severity=severity,
        status=ConflictStatus.DETECTED,
        description=raw.get("description") or "",
        rationale=raw.get("rationale"),
        confidence=raw.get("confidence"),
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
                logger.warning("Conflict parse failed (attempt 1), retrying: %s", e)
                messages.append({"role": "assistant", "content": last_response_text})
                messages.append({
                    "role": "user",
                    "content": f"That response could not be parsed ({e}). "
                    "Return ONLY the JSON object with a top-level 'conflicts' list.",
                })
                continue
            # Graceful degradation: keep the brief's existing conflicts, continue.
            logger.error("Conflict analysis failed after retry — keeping existing conflicts: %s", e)
            return {"planning_brief": brief, "conflict_prompt": rendered_prompt}

    fresh = [e for e in (_build_entry(r, goals, activities) for r in (raw_conflicts or [])) if e]
    _carry_forward(fresh, prior)
    merged = fresh + _merge_composer(fresh, prior)

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
