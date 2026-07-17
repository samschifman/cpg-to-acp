# CPG-to-ACP Project Plan

> **Note:** This plan is directional. Phases, priorities, and technology choices are subject to change as the project evolves and as the Red Hat AI platform matures. Phase ordering beyond Phase 3 may be adjusted based on priorities and dependencies.

## Goal

Transform Clinical Practice Guidelines into patient-specific, FHIR-compliant, actionable care plans — running on OpenShift with Red Hat AI platform capabilities. Enable parallel development across areas with cross-cutting milestones.

## Current State (Phase 1 Complete)

The walking skeleton is operational: synthetic CPG → Docling parsing → LLM DMN extraction → dynamic deployment to acp-writer → JIT evaluation via Kogito → FHIR CarePlan output. Runs locally in podman-compose. REST API + MCP tool definitions. 19 integration tests. Shared contracts in `shared/`.

**What works:** end-to-end pipeline with one synthetic CPG, two patients, deterministic care plans from DMN decision outputs.

**What doesn't exist yet:** multi-agent orchestration, vector store, recommendation extraction, UIs, OpenShift deployment, real CPGs, BPMN output, automation service, governance.

---

## Phases

### Phase 2 — OpenShift + OpenShell + Platform Foundation

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

#### cpg-ingester

| Work | Notes |
|---|---|
| Add filtering agent — identifies relevant vs. irrelevant CPG sections | Uses selected agent framework |
| Add decision identification agent — clearly identifies decisions vs. process/recommendations | — |
| Add DMN writing agent — produces high-quality DMN with validation | Replace single-prompt extraction |
| Add recommendation extraction agent — extracts process/recommendations for vector store | Contract format TBD |
| Incorporate AutoRAG for retrieval optimization (if it makes sense) | AutoRAG |
| Wire agents together using selected orchestration approach | Framework from Phase 2 spike |

#### acp-writer

| Work | Notes |
|---|---|
| Establish vector store for recommendations | Pluggable (Milvus, pgvector) |
| Enhance care plan composition agent — uses DMN + retrieved recommendations | Replace hardcoded mapping |
| Generate CarePlan with narrative activities from process/recommendations | Activities reference CPG source |
| Add FHIR CarePlan expert agent — correct codes, AI Transparency on FHIR IG compliance | Research: HL7 AIToF IG |
| **Research:** What makes effective goals in a FHIR CarePlan? | Clinical + FHIR standard input |
| Write CarePlan + associated resources back to HAPI FHIR server | — |
| Accept patient data as IPS instead of raw Bundle | Replace Phase 1 shortcut |

#### Minimal UIs

| Component | Work | Notes |
|---|---|---|
| **cpg-ingester** | Upload CPG (PDF) and review/approve extracted decisions and recommendations | Simple workflow: upload → review → approve → push to acp-writer |
| **acp-writer** | Review and approve a generated care plan | Simple workflow: submit patient data → review CarePlan → approve |

These are functional but minimal — interactive editing, side-by-side CPG comparison, and BPMN visualization come in later phases.

#### platform

| Work | Notes |
|---|---|
| OpenShell policies per agent (network, filesystem, credential scoping) | OpenShell |
| MCP Gateway for governed tool access | MCP Gateway |

#### Exit Criteria

- cpg-ingester is a multi-agent pipeline that extracts both DMN and recommendations
- acp-writer produces CarePlans with recommendation-backed narrative activities
- Vector store operational with recommendation retrieval
- Minimal UIs allow upload, review, and approval for both ingestion and care plan generation
- Agent sandboxing via OpenShell

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

| Phase | Technologies Added |
|---|---|
| Phase 1 (complete) | Docling, LiteLLM (local), Drools/Kogito |
| Phase 2 | OpenShift, OpenShell, MaaS, MLflow, MCP |
| Phase 3 | AutoRAG, MCP Gateway, vector store |
| Phase 4 | — (BPMN generation, no new platform tech) |
| Phase 5 | NeMo Guardrails, EvalHub, Garak, vLLM, Praxis |
| Phase 6 | Keycloak, SPIFFE/SPIRE |
| Phase 7 | SMART on FHIR |

## Parallel Development Tracks

Each area can advance semi-independently within a phase. Cross-cutting dependencies are noted in the phase tables. The key synchronization points are:

1. **Agent framework selection (Phase 2 spike)** — blocks all multi-agent work in Phase 3
2. **OpenShift deployment (Phase 2)** — blocks OpenShell, MaaS
3. **Vector store + recommendation contract (Phase 3)** — blocks recommendation-backed care plans
4. **BPMN contract in shared/ (Phase 4)** — blocks automation service integration
5. **Keycloak + OIDC (Phase 6)** — blocks SMART on FHIR launch in Phase 7

Within each phase, a contributor can pick up any work item in their area without blocking others, as long as the phase's prerequisites are met.

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
