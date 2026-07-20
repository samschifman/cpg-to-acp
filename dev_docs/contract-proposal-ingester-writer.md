# Contract Proposal: cpg-ingester ↔ acp-writer

**Date:** 2026-07-20
**Status:** Proposal for review
**Context:** Phase 3.0 gate — these contracts must be defined before Phase 3.1 (cpg-ingester) and Phase 3.2 (acp-writer) can proceed independently.

---

## Principles

1. **Neither component imports from the other.** All contracts live in `shared/`.
2. **Standards as contracts.** DMN is the standard for computable decisions. The recommendation contract defined here is the standard for non-computable content.
3. **Computable criteria belong in DMN, not recommendations.** Population applicability criteria (age ranges, diagnosis codes, lab thresholds) are decision inputs. Only non-computable scope notes travel with recommendations.
4. **Metadata is not optional.** A recommendation without certainty, source, and type metadata is unusable for care plan generation.
5. **The contracts must support independent testing.** cpg-ingester validates output against contract schemas. acp-writer tests against hand-crafted fixture data.

---

## Communication Surface

cpg-ingester sends two categories of artifacts to acp-writer:

```
cpg-ingester ──── DMN XML ────────────► acp-writer (decision engine)
             ├─── Recommendations ────► acp-writer (vector store)
             └─── CPG Metadata ───────► acp-writer (guideline registry)
```

Each has its own contract. All three flow through acp-writer's REST API (and MCP tools), using contract types defined in `shared/`.

---

## Contract 1: CPG Metadata

Guideline-level information that applies to all artifacts extracted from a single CPG. Sent once per ingested guideline. Both decision models and recommendations reference this by `cpg_id`.

```python
class GradingSystem(str, Enum):
    GRADE = "GRADE"
    COR_LOE = "COR-LOE"
    GRADE_COR_HYBRID = "GRADE-COR-hybrid"
    SIMPLIFIED = "simplified"
    VERB_IMPLIED = "verb-implied"
    UNGRADED = "ungraded"

class GuidelineArchetype(str, Enum):
    INSTITUTIONAL = "institutional"
    JOURNAL_ARTICLE = "journal-article"
    MULTI_MODULE = "multi-module"
    FOCUSED_POLICY = "focused-policy"

class CPGMetadata(BaseModel):
    cpg_id: str                          # e.g., "SYN-HTN-2026-001"
    title: str
    version: str | None = None
    publication_date: date | None = None
    evidence_review_date: date | None = None  # "based on evidence reviewed through..."
    issuing_body: str | None = None       # kept generic, not used for filtering
    archetype: GuidelineArchetype | None = None
    grading_system: GradingSystem | None = None
    scope: str | None = None              # target population / clinical condition
    supersedes: str | None = None         # cpg_id of the guideline this replaces
```

**Why this exists separately from recommendations:** A single CPG produces many decision models and many recommendations. The guideline-level metadata (grading system, archetype, scope) applies to all of them and should not be duplicated on every artifact.

**API endpoint:** `POST /api/v1/guidelines` → registers a CPG, returns `cpg_id`

---

## Contract 2: Decision Models (DMN) — existing, with refinements

The DMN boundary already works. The contract types exist in `shared/cpg_contracts/decisions.py`. Proposed refinements based on the CPG analysis:

```python
class DecisionVariable(BaseModel):
    name: str
    type: str                            # "string", "number", "boolean"
    description: str | None = None       # what this variable represents clinically
    codes: list[str] | None = None       # SNOMED/LOINC codes for this variable

class DecisionModelSummary(BaseModel):
    id: str
    name: str
    inputs: list[DecisionVariable]
    outputs: list[DecisionVariable]
    deployed_at: datetime | None = None
    source_cpg: str | None = None        # cpg_id reference
    category: str | None = None          # "treatment", "screening", "monitoring", "risk-assessment"
    modifies: str | None = None          # id of another model this overrides for a subpopulation
```

### Refinements from the CPG analysis

1. **`description` on DecisionVariable** — clinicians need to know what "Systolic BP" means in context (office measurement? ambulatory? home?). The CPG analysis found that measurement technique directly affects threshold validity.

2. **`codes` on DecisionVariable** — SNOMED/LOINC codes enable acp-writer to map FHIR patient data to DMN inputs automatically instead of relying on hardcoded field names.

3. **`category` on DecisionModelSummary** — the CPG analysis identified distinct decision types (treatment selection, screening criteria, monitoring schedules, risk stratification). acp-writer needs to know what kind of decision this is to place it correctly in the care plan.

4. **`modifies` on DecisionModelSummary** — the CPG analysis found that subpopulation recommendations are patches/overrides of general recommendations. A CKD-specific treatment decision *modifies* the general treatment decision. This relationship must be explicit so acp-writer can apply the right override chain for a patient's condition profile.

**API endpoint:** `POST /api/v1/decisions/models` (existing) — accepts DMN XML, returns `DecisionModelSummary`

**Transport:** DMN XML is the artifact. The contract types describe the metadata extracted from it.

---

## Contract 3: Recommendations — new

This is the TBD boundary from AGENTS.md. Based on the CPG analysis, recommendations need structured metadata to be useful for care plan generation.

### Core types

```python
class RecommendationStrength(str, Enum):
    STRONG_FOR = "strong-for"
    CONDITIONAL_FOR = "conditional-for"
    CONSENSUS = "consensus"
    NO_RECOMMENDATION = "no-recommendation"
    CONDITIONAL_AGAINST = "conditional-against"
    STRONG_AGAINST = "strong-against"

class EvidenceQuality(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very-low"
    UNGRADED = "ungraded"

class RecommendationType(str, Enum):
    TREATMENT = "treatment"
    DIAGNOSTIC = "diagnostic"
    MONITORING = "monitoring"
    LIFESTYLE = "lifestyle"
    EDUCATIONAL = "educational"
    REFERRAL = "referral"
    SCREENING = "screening"
    CONTRAINDICATION = "contraindication"
    PROCESS = "process"           # workflow/procedural steps

class CertaintyGrade(BaseModel):
    strength: RecommendationStrength
    evidence_quality: EvidenceQuality
    original_grade: str | None = None  # e.g., "1A", "Strong for, moderate certainty"

class CrossReference(BaseModel):
    target_id: str                     # id of the referenced recommendation or decision model
    relationship: str                  # "prerequisite", "alternative", "conflicts-with",
                                       # "modifies", "related", "supersedes"
    description: str | None = None

class Recommendation(BaseModel):
    id: str                            # unique within the source CPG
    source_cpg: str                    # cpg_id reference
    section: str | None = None         # section reference within the CPG (e.g., "3.4", "Rec 12")
    title: str
    content: str                       # the recommendation text
    recommendation_type: RecommendationType
    certainty: CertaintyGrade | None = None
    scope_notes: str | None = None     # non-computable applicability caveats
    remarks: list[str] | None = None   # structured implementation context bullets
    rationale: str | None = None       # why this recommendation was made
    cross_references: list[CrossReference] | None = None
    provenance: str | None = None      # lifecycle status: "reviewed", "new-added",
                                       # "amended", "not-changed"
    evidence_review_date: date | None = None  # when the evidence for THIS recommendation
                                               # was last reviewed (may differ from CPG date)
```

### Bundle type for batch ingestion

```python
class RecommendationBundle(BaseModel):
    source_cpg: str                    # cpg_id reference
    recommendations: list[Recommendation]
```

### Design decisions explained

**Why `content` is a single string, not structured sub-fields:** The CPG analysis found that recommendation content ranges from one-line statements to multi-paragraph guidance with embedded lists. Forcing structure (e.g., separate `action`, `condition`, `population` fields) would require the extraction system to decompose natural language into a schema that doesn't match how CPGs are written. Instead, the content is the recommendation as extracted, and the structured metadata (`recommendation_type`, `certainty`, `cross_references`) provides the machine-readable dimensions.

**Why `certainty` is a nested object, not flat fields:** The normalized certainty schema maps five different grading systems into a common representation. The `original_grade` preserves the source system's exact label so nothing is lost in normalization. This was a key finding from the CPG analysis — the two-axis structure (strength × evidence quality) is universal but the labels vary dramatically.

**Why `no-recommendation` is a strength value:** The CPG analysis validation found that formal "no recommendation for or against" is a distinct output that needs explicit capture — different from silence (topic not addressed) and from a conditional recommendation.

**Why `remarks` is a separate field:** The validation found structured bulleted "Remarks" sections attached to individual recommendations with practical implementation details. These sit between the recommendation and the evidence discussion and are a distinct extraction target.

**Why `scope_notes` is a string, not structured:** Non-computable applicability caveats ("studied primarily in US veterans", "limited evidence in pregnant populations") are free text by nature. Computable criteria belong in DMN, not here.

**API endpoints:**
- `POST /api/v1/knowledge/recommendations` → ingest a single recommendation
- `POST /api/v1/knowledge/recommendations/batch` → ingest a `RecommendationBundle`
- `GET /api/v1/knowledge/recommendations?source_cpg=...` → list by CPG
- `POST /api/v1/knowledge/search` → semantic search (unchanged)

---

## Contract 4: Search — refinement of existing

The existing `KnowledgeSearchRequest` / `KnowledgeSearchResponse` need updates to surface the new metadata:

```python
class RecommendationSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    source_cpg: str | None = None         # scope to a specific CPG
    recommendation_type: RecommendationType | None = None  # filter by type
    min_strength: RecommendationStrength | None = None     # floor for strength

class RecommendationSearchResult(BaseModel):
    recommendation: Recommendation        # full recommendation with metadata
    score: float                          # similarity score
    excerpt: str | None = None            # highlighted matching text

class RecommendationSearchResponse(BaseModel):
    results: list[RecommendationSearchResult]
```

**Why type and strength filters:** acp-writer composes care plans by type — it needs treatment recommendations separately from lifestyle recommendations. And a care plan that only surfaces strong recommendations for a first pass, with conditional recommendations available on expansion, needs strength filtering.

---

## What does NOT cross this boundary

These are internal to one component and do not appear in the contracts:

- **Vector store implementation** — internal to acp-writer (Milvus, pgvector, etc.)
- **Extraction pipeline state** — internal to cpg-ingester (LangGraph graph state, agent outputs)
- **Embedding model choice** — internal to acp-writer
- **Docling parse output** — internal to cpg-ingester (Markdown, JSON)
- **LLM prompts** — internal to cpg-ingester
- **FHIR CarePlan structure** — output of acp-writer, not part of this boundary
- **Patient data** — input to acp-writer from mock-EHR, not from cpg-ingester

---

## How the contracts relate

```
                    CPGMetadata
                    (registered once per guideline)
                         │
            ┌────────────┼────────────┐
            │            │            │
     DecisionModel   Recommendation  Recommendation
     (DMN XML +      (treatment)     (lifestyle)
      metadata)           │               │
            │            └───────────────┘
            │                    │
            │         ┌─────────┴──────────┐
            │         │  CrossReference    │
            │         │  (links between    │
            │         │   recommendations  │
            │         │   and/or decisions) │
            │         └────────────────────┘
            │
       modifies ──► DecisionModel
       (subpopulation override)
```

A `CPGMetadata` is the parent. It has many `DecisionModel`s and many `Recommendation`s. Decision models can modify other decision models (subpopulation overrides). Recommendations can cross-reference other recommendations or decision models.

---

## Changes to existing contracts

| What | Change | Reason |
|---|---|---|
| `DecisionVariable` | Add `description`, `codes` | Clinical context and FHIR mapping |
| `DecisionModelSummary` | Add `category`, `modifies` | Decision type classification and subpopulation override chain |
| `KnowledgeDocument` (OpenAPI) | Replace with `Recommendation` | Structured metadata instead of freeform `metadata: {}` |
| `KnowledgeSearchRequest` | Replace with `RecommendationSearchRequest` | Type and strength filtering |
| `KnowledgeSearchResponse` | Replace with `RecommendationSearchResponse` | Full recommendation in results |
| AGENTS.md | Change "Recommendations: TBD" to the contract name | Close the open boundary |

### What stays the same

| What | Why |
|---|---|
| DMN XML as the artifact format | DMN is the standard; the contract types describe metadata, not the artifact |
| `DecisionEvaluationRequest` / `Response` | Evaluation contract is between acp-writer and its internal decision engine, not part of the ingester↔writer boundary |
| `PatientSummary` (fhir.py) | This is the mock-EHR↔acp-writer boundary, not ingester↔writer |
| REST API structure | Same endpoint patterns, updated schemas |

---

## File layout in `shared/`

```
shared/src/cpg_contracts/
├── __init__.py          # re-exports all types
├── decisions.py         # DecisionVariable, DecisionModelSummary,
│                        # DecisionEvaluationRequest/Response (refined)
├── recommendations.py   # NEW: Recommendation, RecommendationBundle,
│                        # CertaintyGrade, CrossReference, enums
├── guidelines.py        # NEW: CPGMetadata, GradingSystem, GuidelineArchetype
├── search.py            # NEW: RecommendationSearchRequest/Response/Result
└── fhir.py              # PatientSummary (unchanged — different boundary)
```

---

## Open questions for review

1. **Should `Recommendation.content` support structured content (lists, sub-sections) or is plain text sufficient?** The CPG analysis found lifestyle modifications are often bulleted lists. Options: (a) plain text with markdown formatting, (b) a `content_items: list[str]` for bulleted content alongside the main `content` string.

2. **Should `CrossReference.target_id` reference recommendations by their `id` within a CPG, or by a globally unique identifier?** If a recommendation references a decision model, the target_id needs to work across both namespaces.

3. **Should the `modifies` relationship on `DecisionModelSummary` be a single reference or a list?** A CKD-specific AND frailty-specific model might modify the same base model.

4. **Should `CertaintyGrade` include the grading system identifier, or is that always inherited from `CPGMetadata`?** Some CPGs use GRADE-CERQual alongside traditional GRADE for different types of evidence within the same guideline.

5. **Do we need a separate `Contraindication` type, or is `recommendation_type: "contraindication"` with `cross_references` sufficient?** Contraindications are "don't do X when Y" — they cross-reference a treatment recommendation and negate it under specific conditions.
