# Contract Review Findings

**Date:** 2026-07-20
**Reviewer:** Independent agent with no involvement in contract design
**Input:** `dev_docs/contract-proposal-ingester-writer.md`, `dev_docs/cpg-analysis.md`, existing code

---

## Strengths (6 confirmed)

1. DMN/recommendation split correctly drawn — population applicability in DMN, scope notes in recommendations
2. CPGMetadata as a separate parent entity avoids duplication
3. Normalized certainty schema is the right abstraction (two-axis, original grade preserved)
4. "What does NOT cross this boundary" section prevents scope creep
5. Design decisions are explained with traceability to CPG analysis findings
6. Directional strength values preserve intent needed by acp-writer

## Issues Found

### HIGH severity (6) — must fix before implementation

| # | Issue | Fix |
|---|---|---|
| H1 | `CrossReference.relationship` is a free string | Define `CrossReferenceRelationship` enum |
| H2 | `Recommendation.provenance` is a free string | Define `RecommendationProvenance` enum |
| H3 | `DecisionModelSummary.category` is a free string | Define `DecisionCategory` enum (or reuse `RecommendationType`) |
| H4 | `min_strength` filter has undefined ordering (direction ≠ intensity) | Replace with `strength_in: list[RecommendationStrength]` for explicit selection |
| H5 | ID generation conflict — proposal says GUIDs, existing code derives from name | Decide who generates IDs; cpg-ingester generates, acp-writer preserves |
| H6 | No CRUD endpoints for guidelines resource | Add GET (list/retrieve), DELETE (with cascade behavior) |

### MEDIUM severity (8) — should fix before implementation

| # | Issue | Fix |
|---|---|---|
| M1 | No contract versioning mechanism | Add `schema_version` or document API versioning strategy |
| M2 | `supersedes` should be a list (unified guidelines replace multiple) | Change to `list[str]` |
| M3 | Search returns full Recommendation objects (heavy payload) | Return `RecommendationSummary` in search; full details via GET by id |
| M4 | No language field on CPGMetadata | Add `language: str` (BCP-47 tag) |
| M5 | `archetype` field serves cpg-ingester, not acp-writer | Remove from contract or document acp-writer use case |
| M6 | Inheritance rule for `CertaintyGrade.grading_system` when None is undocumented | Document: "If None, inherit from CPGMetadata" |
| M7 | `DecisionVariable.type` underspecified vs DMN's type system | Define `DecisionVariableType` enum including date, datetime, duration |
| M8 | OpenAPI and Python types disagree on `source_cpg` placement | Reconcile — both should have it on summary |

### LOW severity (7) — worth considering

| # | Issue | Fix |
|---|---|---|
| L1 | No batch endpoint for decision models | Add batch endpoint for atomic multi-model deployment |
| L2 | No `content_format` discriminator for text vs markdown | Mandate markdown (plain text is valid markdown) |
| L3 | Cross-references to external (un-ingested) guidelines have no representation | Add `target_type: "internal" | "external"` |
| L4 | Two ways to represent "ungraded" (certainty=None vs UNGRADED enum) | Document convention: CPG-level UNGRADED + recommendation-level certainty=None |
| L5 | `cross_references` may be unreliable from LLM extraction | State best-effort; acp-writer also uses semantic search |
| L6 | `consensus` has no directional variant (for/against) | Accept — consensus-against is rare; direction in content text is sufficient |
| L7 | URL path inconsistency (`/guidelines` vs `/knowledge/recommendations`) | Use `/api/v1/knowledge/guidelines` for consistency |
