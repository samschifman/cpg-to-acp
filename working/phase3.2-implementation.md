# Phase 3.2 Implementation Plan — acp-writer Multi-Agent Composition

## Context

Phase 3.1 is complete: cpg-ingester is a multi-agent pipeline that produces DMN and recommendations in the shared contract format. Phase 3.2 replaces the hardcoded care plan composition in acp-writer with a LangGraph multi-agent pipeline that uses DMN decisions, retrieved recommendations, and FHIR expertise.

The legacy acp-writer had 4 source files with hardcoded hypertension logic. Steps 0–17 are complete: all 11 pipeline nodes implemented, legacy `careplan.py` removed, E2E tests written. Step 18 (UI) is the final step.

**Branch:** `feature/phase3.2-acp-writer`
**Design doc:** `dev_docs/acp-writer-design.md`
**Contracts:** `shared/src/cpg_contracts/` (CPGMetadata, Recommendation, DecisionModelSummary, SourceLocation)
**Test data:** `shared/tests/fixtures/sample-recommendations.json`, `mock-EHR/data/patient-bundle-*.json`
**Existing tests:** `acp-writer/tests/test_integration.py`

### Resolved design questions

- **IPS parsing:** Lazy extraction — Condition Scanner extracts codes first, DMN Executor does targeted extraction on-demand. No full upfront parse.
- **Planning Brief:** Formal Pydantic schema — contract between LLM reasoning and deterministic FHIR generator. Carries extra workflow context for future BPMN.
- **FHIR generation:** Deterministic code, not LLM. Eliminates code hallucination.
- **Terminology:** Verified during composition (Plan Composer uses terminology tool) + safety net (Terminology Validator after FHIR generation).
- **AI Transparency:** Built in — AIAST tags, AI-Device, AI-Provenance are first-class outputs of FHIR Bundle Generator.
- **Conflict resolution:** Placeholder detection only. Full interactive resolution deferred.
- **Vector store:** Spike required before implementation. User leans PostgreSQL + pgvector.
- **Deployment:** Single pod for Phase 3.2. Pod-per-security-profile in Phase 3.3.
- **Checkpointing:** MemorySaver for dev, SqliteSaver for production-lite (Phase 3.3).

---

## Step 0: Vector store spike ✅

**Goal:** Evaluate and select a vector store for recommendation storage and retrieval.

### Tasks

- [x] Evaluate PostgreSQL + pgvector:
  - Semantic search quality with recommendation embeddings
  - Hybrid search: metadata filters (source_cpg, recommendation_type, strength) + vector similarity
  - Indexing performance with 100-1000 recommendations
  - Operational complexity (single database for metadata + vectors)
  - OpenShift deployment (PostgreSQL operator available on RHOAI)
- [x] Evaluate Milvus:
  - Same criteria as above
  - Additional infrastructure requirements
- [x] Evaluate ChromaDB:
  - Same criteria, note production readiness limitations
- [x] Select embedding model (sentence-transformers or OpenAI embeddings via LiteLLM)
- [x] Write spike findings to `dev_docs/spike-vector-store.md`

### Verify

- Selected option handles hybrid search (metadata + vector) correctly
- Can store and retrieve Recommendation objects with all contract fields
- Operational complexity is acceptable for the project

---

## Step 1: Project scaffolding and dependencies ✅

**Goal:** Add LangGraph, vector store, and FHIR dependencies. Create module structure.

### Tasks

- [x] Add dependencies to `acp-writer/pyproject.toml`:
  - `langgraph>=0.4` (StateGraph, MemorySaver)
  - `langchain-openai>=0.3` (LLM integration)
  - Vector store client (based on spike: `pgvector`, `asyncpg`, `sqlalchemy`)
  - Embedding model library (`sentence-transformers`)
  - Keep existing: `fastapi`, `uvicorn`, `requests`, `click`, `cpg-contracts`, `mlflow`, `mcp`
- [x] Create new source files (empty stubs):
  - `acp_writer/pipeline.py` — main LangGraph graph definition
  - `acp_writer/state.py` — `CarePlanComposerState` TypedDict
  - `acp_writer/planning_brief.py` — formal Pydantic schema
  - `acp_writer/nodes/` package:
    - `condition_scanner.py`
    - `guideline_resolver.py`
    - `dmn_executor.py`
    - `recommendation_retriever.py`
    - `plan_composer.py`
    - `brief_reviewer.py`
    - `fhir_bundle_generator.py`
    - `terminology_validator.py`
    - `fhir_syntax_validator.py`
    - `fhir_semantic_reviewer.py`
    - `fhir_server_writer.py`
  - `acp_writer/tools/` package:
    - `terminology_lookup.py` — multi-system code find/verify
    - `ips_extractor.py` — targeted data extraction from IPS
  - `acp_writer/validators/` package:
    - `fhir_syntax.py` — structural validation
    - `fhir_bundle_builder.py` — deterministic FHIR generation
  - `acp_writer/store/` package:
    - `vector_store.py` — pluggable vector store interface
    - `guidelines_store.py` — CPGMetadata storage
  - `acp_writer/prompts/` — prompt templates for LLM agents
- [x] Create test structure: `acp-writer/tests/`
  - `test_state.py`
  - `test_planning_brief.py`
  - `test_pipeline.py` (integration)
  - `test_terminology.py`
  - `test_fhir_builder.py`
  - `test_validators.py`
- [ ] Set up MLflow tracing: `mlflow.langchain.autolog()` in pipeline entrypoint (deferred to Step 4 when pipeline is wired)
- [x] Keep existing API endpoints working — don't break them until replacements are tested

### Verify

- All imports succeed
- Existing tests still pass
- New test stubs run

---

## Step 2: Guidelines CRUD + recommendation ingestion endpoints ✅

**Goal:** Implement the API endpoints cpg-ingester's Delivery Agent needs. This is a prerequisite for testing with real cpg-ingester output.

### Tasks

- [x] Implement guidelines store (`store/guidelines_store.py`)
- [x] Implement API endpoints in `api.py` (guidelines CRUD)
- [x] Implement recommendation ingestion endpoints (single, batch, list, get)
- [x] Remove old 501 stubs for `/knowledge/documents`
- [x] Store recommendations in vector store (embed on ingest)
- [x] Implement search endpoint with vector similarity + metadata filters
- [x] Update MCP server with missing tools
- [x] Implement pluggable EmbeddingProvider interface
- [x] Test with sample-recommendations.json fixture (24 tests)

### Verify

- cpg-ingester's mock_receiver pattern works (POST guidelines → POST DMN → POST recs)
- Recommendations are searchable after ingestion
- Metadata filters work correctly
- Cascade delete removes guidelines + associated models + recommendations

---

## Step 3: Planning Brief Pydantic schema ✅

**Goal:** Define the formal contract between Phase 1 (LLM reasoning) and Phase 2 (deterministic FHIR generation).

### Tasks

- [x] Define Pydantic models: PlanningBrief, PlanGoal, PlanActivity, ActivityWorkflow, DMNAuditEntry, FHIRCode, TargetValue, ConflictEntry, ReviewStatus
- [x] Include BPMN-forward context fields (actor, sequencing, escalation, monitoring_trigger)
- [x] Write serialization tests: roundtrip, validation, hypertension scenario (25 tests)

### Verify

- Schema validates the example JSON from the design doc
- Missing required fields raise ValidationError
- Extra workflow context fields serialize correctly

---

## Step 4: State schema and pipeline skeleton ✅

**Goal:** Define LangGraph state and wire up the full graph with stub nodes.

### Tasks

- [x] Implement `CarePlanComposerState` TypedDict with all Phase 1/Phase 2 fields
- [x] Build 11-node graph with two conditional review loops (max 2 each)
- [x] Configure MemorySaver checkpointer
- [x] File output infrastructure (`output.py`)
- [x] All nodes initially stubs, wired into pipeline (10 tests)

### Verify

- Graph compiles and runs with stub nodes
- Graph has expected nodes
- MemorySaver allows resume

---

## Step 5: Condition Scanner node ✅

**Goal:** Lightweight deterministic extraction of condition codes from IPS.

### Tasks

- [x] Deterministic FHIR traversal: conditions, medications, allergies, demographics
- [x] Handles IPS and raw FHIR Bundles, filters inactive/resolved
- [x] MLflow traced, wired into pipeline (10 tests)

### Verify

- Extracts known conditions from test patient bundles
- Handles IPS and raw Bundle formats
- Does NOT extract observations or full patient history

---

## Step 6: Guideline Resolver node ✅

**Goal:** Match patient conditions to registered CPGs and DMN models.

### Tasks

- [x] Condition-to-CPG scope text matching
- [x] DMN dependency graph from DecisionModelSummary.modifies with topological order
- [x] Preserves model insertion order within dependency levels
- [x] MLflow traced, wired into pipeline (12 tests)

### Verify

- Matches hypertension CPG to patient with hypertension conditions
- Does NOT match unrelated CPGs
- Builds correct dependency graph for treatment → monitoring chain

---

## Step 7: Terminology lookup tool ✅

**Goal:** Reusable tool for FHIR code find/verify, used by Plan Composer and Terminology Validator.

### Tasks

- [x] SNOMED, RxNorm, LOINC, ICD-10-CM find/verify via public APIs
- [x] 30-day TTL in-memory cache, graceful network degradation
- [x] `verify_bundle_codes()` walks all coded fields in a FHIR Bundle
- [x] MLflow traced (25 tests: 10 offline + 15 network)

### Verify

- Finds correct SNOMED code for "hypertension"
- Verifies known LOINC codes
- Returns `not-found` for fabricated codes
- Network errors are handled gracefully

---

## Step 8: IPS targeted extraction tool ✅

**Goal:** Tool that the DMN Executor calls to extract specific data points from the IPS.

### Tasks

- [x] extract_observation (most recent by code, handles panel components)
- [x] extract_condition, extract_medication, extract_allergy
- [x] Each returns ExtractionResult with value, unit, date, FHIR reference
- [x] MLflow traced (22 tests)

### Verify

- Extracts systolic BP from patient-bundle-medication.json
- Returns FHIR resource reference for provenance chain
- Returns None for data not present in the IPS

---

## Step 9: DMN Executor node ✅

**Goal:** Execute applicable DMN models with targeted IPS extraction.

### Tasks

- [x] Topological execution from dependency graph
- [x] Known-variable mapping (LOINC/SNOMED) + flexible prior-result chaining
- [x] Full audit trail with inputs, outputs, FHIR references, timestamps
- [x] Graceful failure with error recording, missing input warnings
- [x] MLflow traced, wired into pipeline (10 tests)

### Verify

- Evaluates treatment recommendation model with correct patient data
- Chains monitoring plan evaluation using treatment recommendation output
- Records complete audit trail
- Handles evaluation failures gracefully

---

## Step 10: Recommendation Retriever node ✅

**Goal:** Search vector store for applicable recommendations.

### Tasks

- [x] Builds natural language query from conditions + DMN outputs
- [x] Searches vector store per applicable CPG, deduplicates results
- [x] Returns full Recommendation objects
- [x] MLflow traced, wired into pipeline (9 tests)

### Verify

- Retrieves treatment recommendations for hypertension patient
- Respects source_cpg filter
- Returns recommendations with certainty grades and source locations

---

## Step 11: Plan Composer node ✅

**Goal:** Core clinical reasoning — maps decisions + recommendations to goals + activities.

### Tasks

- [x] LLM maps DMN results + recommendations → PlanningBrief
- [x] Prompt with clinical reasoning, terminology rules, workflow context
- [x] Conflict sanitization (coerces LLM-produced conflicts into ConflictEntry)
- [x] Writes planning-brief.json artifact
- [x] MLflow traced, wired into pipeline (14 tests)

### Verify

- Produces valid PlanningBrief (passes Pydantic validation)
- Goals have LOINC target measure codes
- Activities have verified medication/procedure codes
- Provenance chain links activities to source recommendations

---

## Step 12: Brief Reviewer node (adversarial) ✅

**Goal:** Independent clinical review of the Planning Brief.

### Tasks

- [x] Clinical pharmacist persona, distinct from Plan Composer
- [x] Two-tier: deterministic schema gate → LLM clinical coherence review
- [x] APPROVE/REVISE protocol, max 2 loops, writes review artifact
- [x] MLflow traced, wired into pipeline (10 tests)

### Verify

- Valid brief passes review
- Invalid brief (missing goal, wrong code) triggers revision
- Max 2 iterations, then proceed with flags

---

## Step 13: FHIR Bundle Generator (deterministic) ✅

**Goal:** Produce valid FHIR R4 Bundle from Planning Brief — pure code, no LLM.

### Tasks

- [x] Transaction bundle with CarePlan, Goal, MedicationRequest, ServiceRequest, inline performedActivity
- [x] AI-Device, AI-Provenance, per-activity Provenance, AIAST meta.security
- [x] urn:uuid fullUrls, all references wired, entry.request for transaction
- [x] Wired into pipeline (19 tests)

### Verify

- Produces valid FHIR Bundle (parseable as JSON, correct resourceType on every entry)
- All references resolve within the bundle
- AIAST meta.security on every resource
- AI-Device and AI-Provenance present
- Per-activity Provenance links to source recommendations

---

## Step 14: Terminology Validator + FHIR Syntax Validator ✅

**Goal:** Deterministic validation of the generated FHIR Bundle.

### Tasks

- [x] Terminology Validator: walks coded fields, verifies via terminology tool
- [x] FHIR Syntax Validator: required fields, references, coded fields, AI Transparency
- [x] Both deterministic, wired into pipeline (15 tests)

### Verify

- Valid bundle passes both validators
- Missing AIAST tag is caught
- Invalid code is detected and flagged
- Broken reference is caught

---

## Step 15: FHIR Semantic Reviewer node ✅

**Goal:** LLM review of FHIR Bundle for clinical coherence.

### Tasks

- [x] Clinical informaticist persona, receives syntax + terminology context
- [x] APPROVE/REVISE with feedback loop to FHIR Bundle Generator (max 2)
- [x] MLflow traced, wired into pipeline (7 tests)

### Verify

- Valid bundle passes
- Bundle with orphaned goal triggers revision
- Max 2 iterations

---

## Step 16: FHIR Server Writer + care plan status management ✅

**Goal:** Write care plan to HAPI FHIR and support approve/reject workflow.

### Tasks

- [x] POST transaction Bundle to FHIR server, graceful fallback to local storage
- [x] Care plan CRUD: list (patient/status filters), get, approve, reject
- [x] Approval: AIAST → CLINAST_AIRPT, clinician verifier on Provenance
- [x] Rejection: status → revoked, reason in CarePlan.note
- [x] API endpoints updated (were 501 stubs), wired into pipeline (13 tests)

### Verify

- Bundle is written to HAPI FHIR server
- Care plan is retrievable after creation
- Approval changes status and AI Transparency tags
- Rejection records reason

---

## Step 17: End-to-end integration and golden test cases ✅

**Goal:** Validate the full pipeline against known outputs.

### Tasks

- [x] Legacy `careplan.py` removed — all generation uses LangGraph pipeline
- [x] `POST /api/v1/careplans` invokes full pipeline
- [x] CLI updated with `--litellm-url`, `--model`, `--api-key`
- [x] MCP `generate_careplan` uses pipeline
- [x] E2E tests gated behind LITELLM_URL (medication, lifestyle, no-guidelines)
- [x] README rewritten with full architecture
- [x] Pipeline logging with node entry markers and LLM timing

### Verify (Phase 3.2 Exit Criteria)

- [x] acp-writer produces CarePlans with recommendation-backed narrative activities
- [x] Vector store operational with recommendation retrieval
- [x] Knowledge ingestion and guidelines CRUD endpoints functional
- [x] Care plan composition uses both DMN decisions and retrieved recommendations
- [x] Planning Brief validated by adversarial reviewer before FHIR generation
- [x] FHIR output passes terminology, syntax, and semantic validation
- [x] AI Transparency on FHIR IG compliant (AIAST tags, AI-Device, AI-Provenance)
- [x] Care plans written to HAPI FHIR server
- [x] Approval workflow changes AIAST → CLINAST_AIRPT
- [ ] All agents traced in MLflow (tracing infrastructure in place; full trace verification pending E2E)

---

## Step 18: Minimal UI (review + approve)

**Goal:** Simple web UI for care plan review and approval.

### Tasks

- [ ] Implement upload endpoint: accepts IPS Bundle, triggers pipeline
- [ ] Implement review page: shows Planning Brief (goals, activities, conflicts)
- [ ] Implement FHIR view: shows generated CarePlan Bundle
- [ ] Implement approval action: approve/reject with reason
- [ ] Implement results page: delivery status, FHIR server response

### Verify

- Submit patient data → see care plan → approve → verify on FHIR server
- Reject records reason

---

## Files to create/modify

| Path | Action | Step |
|---|---|---|
| `acp-writer/pyproject.toml` | Modify (add deps) | 1 |
| `acp-writer/src/acp_writer/state.py` | Create | 4 |
| `acp-writer/src/acp_writer/pipeline.py` | Create | 4 |
| `acp-writer/src/acp_writer/planning_brief.py` | Create | 3 |
| `acp-writer/src/acp_writer/nodes/__init__.py` | Create | 1 |
| `acp-writer/src/acp_writer/nodes/condition_scanner.py` | Create | 5 |
| `acp-writer/src/acp_writer/nodes/guideline_resolver.py` | Create | 6 |
| `acp-writer/src/acp_writer/nodes/dmn_executor.py` | Create | 9 |
| `acp-writer/src/acp_writer/nodes/recommendation_retriever.py` | Create | 10 |
| `acp-writer/src/acp_writer/nodes/plan_composer.py` | Create | 11 |
| `acp-writer/src/acp_writer/nodes/brief_reviewer.py` | Create | 12 |
| `acp-writer/src/acp_writer/nodes/fhir_bundle_generator.py` | Create | 13 |
| `acp-writer/src/acp_writer/nodes/terminology_validator.py` | Create | 14 |
| `acp-writer/src/acp_writer/nodes/fhir_syntax_validator.py` | Create | 14 |
| `acp-writer/src/acp_writer/nodes/fhir_semantic_reviewer.py` | Create | 15 |
| `acp-writer/src/acp_writer/nodes/fhir_server_writer.py` | Create | 16 |
| `acp-writer/src/acp_writer/tools/__init__.py` | Create | 1 |
| `acp-writer/src/acp_writer/tools/terminology_lookup.py` | Create | 7 |
| `acp-writer/src/acp_writer/tools/ips_extractor.py` | Create | 8 |
| `acp-writer/src/acp_writer/validators/__init__.py` | Create | 1 |
| `acp-writer/src/acp_writer/validators/fhir_syntax.py` | Create | 14 |
| `acp-writer/src/acp_writer/validators/fhir_bundle_builder.py` | Create | 13 |
| `acp-writer/src/acp_writer/store/__init__.py` | Create | 1 |
| `acp-writer/src/acp_writer/store/vector_store.py` | Create | 2 |
| `acp-writer/src/acp_writer/store/guidelines_store.py` | Create | 2 |
| `acp-writer/src/acp_writer/prompts/__init__.py` | Create | 1 |
| `acp-writer/src/acp_writer/api.py` | Modify (add endpoints, replace stubs) | 2, 16 |
| `acp-writer/src/acp_writer/mcp_server.py` | Modify (add missing tools) | 2, 16 |
| `acp-writer/src/acp_writer/careplan.py` | **Removed** at Step 17 (replaced by pipeline) | 17 |
| `acp-writer/tests/test_integration.py` | Modify (update stub tests that expect 501) | 2, 16 |
| `acp-writer/tests/test_planning_brief.py` | Create | 3 |
| `acp-writer/tests/test_state.py` | Create | 4 |
| `acp-writer/tests/test_pipeline.py` | Create | 4 |
| `acp-writer/tests/test_terminology.py` | Create | 7 |
| `acp-writer/tests/test_fhir_builder.py` | Create | 13 |
| `acp-writer/tests/test_validators.py` | Create | 14 |
| `acp-writer/tests/test_e2e.py` | Create | 17 |
| `acp-writer/README.md` | Modify | 17 |
| `dev_docs/spike-vector-store.md` | Create | 0 |

---

## Step dependencies

```
Step 0 (vector store spike)
  │
  ▼
Step 1 (scaffolding) ──────────────────────────────────────┐
  │                                                         │
  ├──► Step 2 (guidelines + recommendations + vector store) │
  │      │                                                  │
  │      └──► Step 10 (Recommendation Retriever)            │
  │                                                         │
  ├──► Step 3 (Planning Brief schema)                       │
  │      │                                                  │
  │      └──► Step 11 (Plan Composer)                       │
  │             │                                           │
  │             ▼                                           │
  │           Step 12 (Brief Reviewer)                      │
  │                                                         │
  ├──► Step 4 (state + skeleton)                            │
  │      │                                                  │
  │      ├──► Step 5 (Condition Scanner)                    │
  │      │      │                                           │
  │      │      ▼                                           │
  │      │    Step 6 (Guideline Resolver)                   │
  │      │      │                                           │
  │      │      ▼                                           │
  │      │    Step 9 (DMN Executor) ◄── Step 8 (IPS tool)   │
  │      │                                                  │
  │      └──► Step 13 (FHIR Bundle Generator)               │
  │             │                                           │
  │             ▼                                           │
  │           Step 14 (Terminology + Syntax Validators)     │
  │             │           ◄── Step 7 (Terminology tool)   │
  │             ▼                                           │
  │           Step 15 (FHIR Semantic Reviewer)              │
  │             │                                           │
  │             ▼                                           │
  │           Step 16 (FHIR Server Writer + status mgmt)    │
  │                                                         │
  └─────────────────────────────────────────────────────────┘
                       │
                       ▼
                    Step 17 (Integration + golden tests)
                       │
                       ▼
                    Step 18 (Minimal UI)
```

Key parallelism opportunities:
- Steps 2, 3, 4, 7, 8 can all start after Step 1
- Steps 5-6-9 (Phase 1 pipeline) and Steps 13-14-15 (Phase 2 pipeline) can be developed in parallel
- Step 11 (Plan Composer) needs Steps 3, 7, 10 complete

---

## Backlog (deferred from this phase)

| Item | Rationale | When |
|---|---|---|
| Full conflict resolution | Requires multi-CPG integration. Placeholder detection only in Phase 3.2. | Phase 3.3+ |
| BPMN generation from Planning Brief | Planning Brief captures workflow context; BPMN Writer deferred. | Phase 4 |
| FHIR server-side validation | Use HAPI FHIR $validate when available. Current validation is client-side structural checks. | Backlog |
| Embedding model evaluation | Initial selection in vector store spike. May need tuning for clinical domain. | Backlog |
| Pod-per-security-profile split | Single pod in Phase 3.2. Split in Phase 3.3 with OpenShell policies. | Phase 3.3 |
| SqliteSaver for persistent checkpointing | MemorySaver for dev. SqliteSaver when UI needs process-restart survival. | Phase 3.3 |
| Research: effective FHIR CarePlan goals | Clinical + FHIR standard input needed for Plan Composer prompt refinement. | During Step 11 |
| Abbreviation expansion in cpg-ingester | Refine Rec Extractor prompt to always expand abbreviations on first use. Do before Phase 3.3. | Between 3.2 and 3.3 |
| PatientSummary allergies field | Contract type lacks allergies — non-blocking but needed if MCP tools expose allergy queries. | Backlog |

### Implementation notes

- **FHIR Bundle type:** The existing `careplan.py` produces `type: "collection"` bundles. The new FHIR Bundle Generator (Step 13) must produce `type: "transaction"` bundles for POST to HAPI FHIR server. Transaction bundles require `entry[].request` with method/url.
- **Planning Brief location:** `acp_writer/planning_brief.py` (internal to acp-writer, NOT in `shared/cpg_contracts/`). This is an implementation detail that may change significantly — keeping it internal avoids cross-component coupling.
- **Legacy code removal:** `careplan.py` is removed at Step 17 after the new pipeline is validated. Update `api.py` and `mcp_server.py` imports at the same time.

---

## Resumption instructions

If this work is interrupted:

1. Read this file to find the current step (first `[ ]`)
2. Read `dev_docs/acp-writer-design.md` for the design rationale
3. Read `dev_docs/project-plan.md` Phase 3.2 for exit criteria
4. Read `AGENTS.md` for architectural boundaries and tracing requirements
5. Check `git log --oneline -10` on `feature/phase3.2-acp-writer` for recent work
6. Check `shared/src/cpg_contracts/` for current contract definitions
7. Check existing `acp-writer/src/acp_writer/api.py` for current endpoint state
8. Resume from the current step — each step has its own verify section
