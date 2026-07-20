# CPG-to-ACP Project Plan

> **Note:** This plan is directional. Phases, priorities, and technology choices are subject to change as the project evolves and as the Red Hat AI platform matures. Phase ordering beyond Phase 3 may be adjusted based on priorities and dependencies.

## Goal

Transform Clinical Practice Guidelines into patient-specific, FHIR-compliant, actionable care plans — running on OpenShift with Red Hat AI platform capabilities. Enable parallel development across areas with cross-cutting milestones.

## Current State (Phase 2 Complete)

The system runs on OpenShift with Red Hat AI platform capabilities. The full pipeline (synthetic CPG → Docling → LLM DMN extraction → deploy to acp-writer → JIT Kogito evaluation → FHIR CarePlan) works both locally via podman-compose and on OpenShift via Helm charts. MaaS routes inference to OpenAI GPT-5.6. MLflow tracing is instrumented across both components. MCP servers expose decision and FHIR tools. Agent framework evaluated (LangGraph recommended). Praxis investigated (too early, Phase 5 target).

**What works:** end-to-end pipeline on OpenShift with one synthetic CPG, two patients, deterministic care plans, MLflow tracing, MaaS inference routing, MCP tool interfaces, NetworkPolicies for service isolation.

**What doesn't exist yet:** multi-agent orchestration, vector store, recommendation extraction, UIs, real CPGs, BPMN output, automation service, full OpenShell sandboxing, MCP Gateway governance.

---

## Phases

### Phase 2 — OpenShift + OpenShell + Platform Foundation (complete)

**Goal:** Get the system running on OpenShift with OpenShell sandboxing and governed inference.

OpenShell can sandbox the existing services without requiring a full multi-agent architecture. Deploying the current acp-writer + decision-service in an OpenShell sandbox on OpenShift establishes the governance pattern early.

#### Work Items

| Area | Work | Technology |
|---|---|---|
| **platform** | Deploy all services to OpenShift (Helm/Kustomize per component) | OpenShift |
| **platform** | Replace LiteLLM with MaaS for inference routing | MaaS |
| **platform** | Wrap acp-writer in OpenShell sandbox with per-binary network policies | OpenShell |
| **platform** | Add MLflow tracing across the pipeline | MLflow |
| **platform** | **Spike:** Agent framework evaluation — compare LangGraph, CrewAI, Rookery, and other options for multi-agent orchestration within cpg-ingester and acp-writer. Must align with OpenShell. | — |
| **platform** | **Spike:** Investigate Praxis as future inference gateway | — |
| **cpg-ingester** | Transition from synthetic to real CPG (VA/DoD guideline) | Docling |
| **cpg-ingester** | Enhance Docling usage: capture diagrams, images, multi-column layouts | Docling |
| **acp-writer** | Implement MCP tool interfaces for FHIR and DMN access | MCP |
| **shared** | Add MCP tool contracts to shared/ | — |
| **mock-EHR** | Verify IPS ($summary) support on HAPI FHIR | — |

#### Exit Criteria

- Pipeline runs on OpenShift
- acp-writer runs inside OpenShell sandbox with visible policy enforcement
- All inference routed through MaaS
- MLflow traces for every pipeline step
- Agent framework decision made (spike complete)
- At least one real CPG processed end-to-end

---

### Phase 3 — Multi-Agent + Knowledge + Minimal UI

**Goal:** Build the multi-agent architecture for both cpg-ingester and acp-writer. Add the recommendation/vector store pipeline. Introduce minimal UIs for upload and approval workflows.

Care plans in this phase include narrative activities based on process/recommendations from the CPG. BPMN generation is deferred to Phase 4.

Phase 3 is split into sub-phases that can advance independently. Phase 3.0 establishes the shared contracts that both sides depend on. After that, Phase 3.1 (cpg-ingester) and Phase 3.2 (acp-writer) can proceed in parallel — neither blocks the other.

---

#### Phase 3.0 — Contracts and Shared Infrastructure

**Goal:** Define the recommendation contract (the last undefined boundary between cpg-ingester and acp-writer) and establish cross-cutting infrastructure so the two tracks can work independently.

| Area | Work | Notes |
|---|---|---|
| **shared** | Define recommendation contract in `shared/` — Pydantic models for recommendations pushed from cpg-ingester to acp-writer | This is the TBD contract from AGENTS.md. Design must cover: source CPG reference, section/context, recommendation text, strength/grade metadata, and any structured content (dosing, timing). |
| **shared** | Define knowledge ingestion API contract — the REST/MCP interface acp-writer exposes for receiving recommendations | Extends the existing 501 stubs (`POST /api/v1/knowledge/documents`, `POST /api/v1/knowledge/search`) |

##### Exit Criteria

- Recommendation contract defined in `shared/` with Pydantic models
- Knowledge ingestion API contract defined (OpenAPI + MCP tool schema)
- Both cpg-ingester and acp-writer teams can implement against the contract independently

---

#### Phase 3.1 — cpg-ingester Multi-Agent Pipeline

**Goal:** Replace the single-prompt DMN extraction with a multi-agent pipeline that extracts both DMN decision tables and narrative recommendations from CPGs.

Can proceed independently after Phase 3.0 contracts are defined. Does not depend on acp-writer's vector store being operational — cpg-ingester outputs recommendations in the contract format and pushes them via the API. If acp-writer's knowledge endpoint isn't ready, cpg-ingester can validate output against the contract schema without a live endpoint.

| Work | Notes |
|---|---|
| Wire agents together using LangGraph (StateGraph) | Framework selected in Phase 2 spike |
| Add filtering agent — identifies relevant vs. irrelevant CPG sections | First node in the graph |
| Add decision identification agent — classifies content as decisions vs. process/recommendations | Splits the pipeline into two tracks |
| Add DMN writing agent — produces high-quality DMN with validation | Replaces single-prompt extraction; validates against golden test cases |
| Add recommendation extraction agent — extracts process/recommendations in the shared contract format | Outputs recommendation contract objects |
| Add push step — sends DMN and recommendations to acp-writer via API/MCP | Extends existing `cpg-deploy-dmn` to also push recommendations |
| Create mock acp-writer receiver — captures DMN and recommendation artifacts to files for review | Lightweight stub that implements the contract API and writes received artifacts to a local directory. Enables testing cpg-ingester end-to-end without a running acp-writer. |
| Incorporate AutoRAG for retrieval optimization (if it makes sense) | AutoRAG |
| Minimal UI: upload CPG (PDF), review/approve extracted decisions and recommendations | Simple workflow: upload → review → approve → push to acp-writer |

##### Exit Criteria

- cpg-ingester is a multi-agent pipeline (LangGraph StateGraph with 4+ nodes)
- Produces both DMN and recommendations in the shared contract format
- DMN validated against golden test cases
- Recommendations validated against the shared contract schema
- Minimal upload/review UI functional
- All agents traced in MLflow

---

#### Phase 3.2 — acp-writer Multi-Agent Composition

**Goal:** Replace the hardcoded care plan composition with a multi-agent system that uses DMN decisions, retrieved recommendations, and FHIR expertise to produce clinically complete care plans.

Can proceed independently after Phase 3.0 contracts are defined. Does not depend on cpg-ingester's multi-agent pipeline — acp-writer can be developed and tested using hand-crafted recommendation data that conforms to the shared contract.

| Work | Notes |
|---|---|
| Implement knowledge ingestion endpoint — accepts recommendations per the shared contract | Replace the 501 stubs with working implementation |
| Establish vector store for recommendations | Pluggable (Milvus, pgvector); internal to acp-writer per AGENTS.md |
| Enhance care plan composition agent — uses DMN + retrieved recommendations | Replace hardcoded mapping with LangGraph-based composition |
| Generate CarePlan with narrative activities from process/recommendations | Activities reference CPG source material |
| Add FHIR CarePlan expert agent — correct codes, AI Transparency on FHIR IG compliance | Research: HL7 AIToF IG |
| **Research:** What makes effective goals in a FHIR CarePlan? | Clinical + FHIR standard input |
| Write CarePlan + associated resources back to HAPI FHIR server | — |
| Accept patient data as IPS instead of raw Bundle | Replace Phase 1 shortcut |
| Minimal UI: review and approve a generated care plan | Simple workflow: submit patient data → review CarePlan → approve |

##### Exit Criteria

- acp-writer produces CarePlans with recommendation-backed narrative activities
- Vector store operational with recommendation retrieval
- Knowledge ingestion endpoint accepts and indexes recommendations
- Care plan composition uses both DMN decisions and retrieved recommendations
- Minimal review/approval UI functional
- All agents traced in MLflow

---

#### Phase 3.3 — Integration, Governance, and End-to-End Testing

**Goal:** Connect cpg-ingester and acp-writer end-to-end, apply governance (OpenShell, MCP Gateway), and validate the complete pipeline.

Requires Phase 3.1 and Phase 3.2 to be substantially complete. This is where the independently-developed tracks are integrated and hardened.

| Area | Work | Notes |
|---|---|---|
| **integration** | End-to-end test: cpg-ingester pushes both DMN and recommendations → acp-writer generates care plans using both | Verify contract compatibility, data flow, error handling |
| **integration** | Validate that recommendations produced by cpg-ingester are correctly indexed and retrieved by acp-writer | Contract fidelity check |
| **integration** | Test with the synthetic CPG end-to-end on OpenShift | Full pipeline on-cluster |
| **platform** | OpenShell policies per agent (network, filesystem, credential scoping) | Deferred from Phase 3.0 — agents must exist before policies can be applied |
| **platform** | MCP Gateway for governed tool access | Deferred from Phase 3.0 — tools must work before governance is layered on |
| **testing** | Golden test cases for the full pipeline (CPG → DMN + recommendations → CarePlan) | Regression suite for future phases |

##### Exit Criteria

- End-to-end pipeline: cpg-ingester → acp-writer produces CarePlans using both DMN and recommendations
- Pipeline runs on OpenShift with MLflow traces visible for every step
- OpenShell agent policies applied and enforced
- MCP Gateway governing tool access
- Golden test cases passing
- All Phase 3.1 and Phase 3.2 exit criteria met

---

### Phase 4 — BPMN + Automation

**Goal:** Add BPMN generation to make care plans actionable. Connect acp-writer to the automation service.

> **Note:** This phase may be reordered relative to Phase 5 depending on project priorities. If governance and evaluation are more urgent, Phase 5 can proceed first.

#### Work Items

| Area | Work | Notes |
|---|---|---|
| **acp-writer** | Add BPMN writing agent — writes BPMN for process/recommendations | — |
| **acp-writer** | Include BPMN in DocumentReferences linked to CarePlan activities via extension | FHIR extension design |
| **acp-writer** | Publish BPMN to automation service on care plan approval | — |
| **automation** | Implement automation service that accepts BPMN from acp-writer | Receives BPMN over API |
| **shared** | Define the BPMN contract in shared/ | — |
| **acp-writer UI** | Add BPMN visualization within care plan review | BPMN renderer |

#### Exit Criteria

- acp-writer generates BPMN for automatable activities
- Automation service receives and stores BPMN
- BPMN visible in the care plan review UI

---

### Phase 5 — Governance + Safety + Evaluation

**Goal:** Quality gates, guardrails, and evaluation pipelines.

#### Work Items

| Area | Work | Technology |
|---|---|---|
| **platform** | NeMo Guardrails on agent I/O — healthcare-specific rules | NeMo Guardrails |
| **platform** | EvalHub — golden test sets per CPG, extraction fidelity scorers, plan quality scorers | EvalHub |
| **platform** | EvalHub gates that block deployment of degraded models/pipelines | EvalHub |
| **platform** | Garak red-teaming for healthcare-specific adversarial scenarios | Garak |
| **platform** | Migrate inference gateway to Praxis (if available) | Praxis |
| **platform** | **Evaluate:** Using smaller self-hosted models (via vLLM) instead of frontier models for cost and latency | vLLM |
| **cpg-ingester** | Validation pipeline: compare extracted DMN against golden test cases | — |
| **acp-writer** | Validate CarePlan output against AI Transparency on FHIR IG | — |
| **acp-writer** | CarePlan quality scoring (automated + clinician review) | — |

#### Exit Criteria

- Guardrails actively filtering agent I/O
- EvalHub gates preventing degraded deployments
- Three audit trails: MLflow (tracing), OpenShell (sandbox), automation (execution)
- AI Transparency on FHIR compliance
- Self-hosted model evaluation complete

---

### Phase 6 — Identity, Auth & Access Control

**Goal:** Establish user authentication, role-based access control, and agent credential scoping so that every action — human or agent — is tied to an authenticated identity with appropriate permissions.

#### Work Items

| Area | Work | Technology |
|---|---|---|
| **platform** | Deploy Keycloak on OpenShift, configure OIDC provider | Keycloak |
| **platform** | Define roles (clinician, admin, reviewer) and map to permissions | Keycloak RBAC |
| **platform** | Agent identity via SPIFFE/SPIRE | SPIFFE/SPIRE |
| **platform** | OpenShell credential scoping — agents run with user-scoped tokens, not shared service accounts | OpenShell + Keycloak |
| **platform** | Audit trail linking actions to authenticated identities | MLflow + OpenShell |
| **acp-writer** | Integrate OIDC auth into UI and API | — |
| **cpg-ingester** | Integrate OIDC auth into UI and API | — |
| **mock-EHR** | Configure HAPI FHIR for token-based access | — |

#### Exit Criteria

- Keycloak running on OpenShift with OIDC configured
- At least three roles (clinician, admin, reviewer) with distinct permissions
- Agent credentials scoped per-user via OpenShell + SPIFFE/SPIRE
- All UIs require authentication; APIs enforce token-based access
- Audit trail links every action to an authenticated identity

---

### Phase 7 — Full UIs + Scale + Demo-Ready

**Goal:** Full user interfaces, multiple CPGs, polished demo.

#### cpg-ingester UI (enhanced)

| Work | Notes |
|---|---|
| Review DMN after conversion — side-by-side with CPG source | Visual comparison |
| Review recommendations before push to acp-writer | — |
| Interactive editing at each step | — |
| Reference back to CPG source for verification | — |

#### acp-writer UI (enhanced)

| Work | Notes |
|---|---|
| Launchable via SMART on FHIR inside supporting EHR | SMART App Launch |
| Pull patient data as IPS from FHIR server for patient in context | — |
| Allow user to add notes about current situation | Free text input |
| Interactive editing of care plan | — |
| Approve → publish to FHIR server + automation service | — |

#### mock-EHR

| Work | Notes |
|---|---|
| Basic EHR UI that supports SMART on FHIR app launch | Consider SMART-EHR-Launcher (CSIRO) |
| Launch acp-writer UI in patient context | EHR launch flow |
| Multiple synthetic patients with varied conditions | — |

#### Scale

| Work | Notes |
|---|---|
| Expand to 3-5 real CPGs (VA/DoD) | — |
| Multi-plan merging when multiple CPGs apply | Conflict detection |
| Conflict resolution with clinician input | — |

#### automation (enhanced)

| Work | Notes |
|---|---|
| Add BPMN execution engine or BPMN-to-Ansible converter | Ansible/SonataFlow |

#### Exit Criteria

- Full UIs for both cpg-ingester and acp-writer
- Mock-EHR launches acp-writer via SMART on FHIR
- 3-5 CPGs with multi-plan merging
- Presentation-ready

---

## Technology Adoption Timeline

| Phase | Status | Technologies Added |
|---|---|---|
| Phase 1 | Complete | Docling, LiteLLM (local), Drools/Kogito |
| Phase 2 | Complete | OpenShift, OpenShell, MaaS, MLflow, MCP |
| Phase 3.0 | Not started | — (contract definitions only) |
| Phase 3.1 | Not started | LangGraph (cpg-ingester agents), AutoRAG |
| Phase 3.2 | Not started | Vector store, MCP Gateway, LangGraph (acp-writer agents) |
| Phase 3.3 | Not started | — (integration and governance) |
| Phase 4 | Not started | — (BPMN generation, no new platform tech) |
| Phase 5 | Not started | NeMo Guardrails, EvalHub, Garak, vLLM, Praxis |
| Phase 6 | Not started | Keycloak, SPIFFE/SPIRE |
| Phase 7 | Not started | SMART on FHIR |

## Parallel Development Tracks

Each area can advance semi-independently within a phase. Cross-cutting dependencies are noted in the phase tables. The key synchronization points are:

1. **Agent framework selection (Phase 2 spike)** — blocks all multi-agent work in Phase 3. Decision: LangGraph (see `dev_docs/spike-agent-framework.md`).
2. **OpenShift deployment (Phase 2)** — blocks OpenShell, MaaS
3. **Recommendation contract (Phase 3.0)** — blocks both Phase 3.1 and Phase 3.2. This is the single gate before cpg-ingester and acp-writer can advance independently.
4. **BPMN contract in shared/ (Phase 4)** — blocks automation service integration
5. **Keycloak + OIDC (Phase 6)** — blocks SMART on FHIR launch in Phase 7

Within Phase 3, the cpg-ingester track (3.1) and acp-writer track (3.2) are designed to advance independently after the shared contracts (3.0) are defined. Neither blocks the other — cpg-ingester validates recommendations against the contract schema, acp-writer tests against hand-crafted recommendation data.

## Backlog — Phase-Independent Tasks

Work that can be picked up at any time, independent of the current phase. These items improve the project but don't block other work.

| Item | Area     | Notes |
|---|----------|---|
| MaaS with Vertex AI (Claude) | platform | Configure MaaS ExternalModel to route to Claude on Vertex AI. Requires a GCP service account key (not ADC user credentials) with the Vertex AI User role, and `oauth2` auth type on the ExternalProvider. OpenAI routing is already working; this adds Claude as a second provider option on-cluster. |
| Enhance tracing in MLflow | all      | Make sure that the use of MLflow is optimized and that traces are useful. |

---

## Open Spikes and Research Items

| Item | Phase | Notes |
|---|---|---|
| Agent framework evaluation | 2 | Compare LangGraph, CrewAI, Rookery, and other options for multi-agent orchestration |
| Praxis investigation | 2 | Emerging inference gateway. Investigate fit and timeline for adoption. |
| Effective FHIR CarePlan goals | 3 | Research what makes clinically meaningful goals — clinical + FHIR standard input needed |
| AI Transparency on FHIR IG | 3 | HL7 STU1 ballot. Defines how to tag FHIR resources generated/influenced by AI |
| Recommendation contract format | 3 | No established standard (unlike DMN/BPMN/FHIR). Design needed. |
| Self-hosted models vs. frontier | 5 | Evaluate using smaller models (via vLLM) for cost, latency, and data locality |
| BPMN-to-Ansible conversion | 7 | Feasibility and approach |
| SMART-EHR-Launcher (CSIRO) | 7 | Open-source EHR simulator for SMART app launch — evaluate for mock-EHR |
