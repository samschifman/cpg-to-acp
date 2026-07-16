# CPG-to-ACP Project Plan v2

## Goal

Demonstrate Clinical Practice Guidelines to Actionable Care Plans on OpenShift with Red Hat AI components — especially OpenShell — as quickly as possible. Enable parallel development across areas with cross-cutting milestones.

## Current State (Phase 1 Complete)

The walking skeleton is operational: synthetic CPG → Docling parsing → LLM DMN extraction → dynamic deployment to acp-writer → JIT evaluation via Kogito → FHIR CarePlan output. Runs locally in podman-compose. REST API + MCP tool definitions. 19 integration tests. Shared contracts in `shared/`.

**What works:** end-to-end pipeline with one synthetic CPG, two patients, deterministic care plans from DMN decision outputs.

**What doesn't exist yet:** multi-agent orchestration, vector store, recommendation extraction, UIs, OpenShift deployment, real CPGs, BPMN output, automation service, governance.

---

## Phases

### Phase 2 — OpenShift + OpenShell + Platform Foundation

**Goal:** Get the system running on OpenShift with OpenShell sandboxing. Demo Red Hat AI governance from the start.

**Why OpenShell first:** OpenShell can sandbox the existing services without requiring a full multi-agent architecture. The fastest path to an OpenShell demo is deploying the current acp-writer + decision-service in an OpenShell sandbox on OpenShift.

#### All Areas

| Area | Work | Red Hat AI Tech |
|---|---|---|
| **platform** | Deploy all services to OpenShift (Helm/Kustomize per component) | OpenShift |
| **platform** | Replace LiteLLM with MaaS for inference routing | MaaS |
| **platform** | Wrap acp-writer in OpenShell sandbox with per-binary network policies | OpenShell |
| **platform** | Add vLLM for self-hosted inference behind MaaS (alongside frontier models) | vLLM |
| **platform** | Add MLflow tracing across the pipeline | MLflow |
| **platform** | **Spike:** Agent framework evaluation — compare Kagenti, LangGraph, CrewAI, Rookery, [fips-agents](https://github.com/fips-agents) for multi-agent orchestration within cpg-ingester and acp-writer. Must align with OpenShell. | — |
| **platform** | **Spike:** Investigate Praxis as future replacement for MaaS/LiteLLM (expected Red Hat AI 3.6, Nov 2026) | — |
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

### Phase 3 — Multi-Agent + Knowledge + Enhanced Extraction

**Goal:** Build the multi-agent architecture for both cpg-ingester and acp-writer. Add the recommendation/vector store pipeline. Make care plans clinically meaningful.

#### cpg-ingester

| Work | Notes |
|---|---|
| Add filtering agent — identifies relevant vs. irrelevant CPG sections | Uses selected agent framework |
| Add decision identification agent — clearly identifies decisions vs. process/recommendations | — |
| Add DMN writing agent — produces high-quality DMN with validation | Replace single-prompt extraction |
| Add recommendation extraction agent — extracts process/recommendations for vector store | Contract format TBD |
| Incorporate AutoRAG for retrieval optimization (if it makes sense) | AutoRAG |
| Wire agents together using selected orchestration approach | Kagenti / framework from spike |

#### acp-writer

| Work | Notes |
|---|---|
| Establish vector store for recommendations | Pluggable (Milvus, pgvector) |
| Enhance care plan composition agent — uses DMN + retrieved recommendations | Replace hardcoded mapping |
| Add FHIR CarePlan expert agent — correct codes, AI Transparency on FHIR IG compliance | Research: HL7 AIToF IG |
| Add BPMN writing agent — writes BPMN for process/recommendations | — |
| **Research:** What makes effective goals in a FHIR CarePlan? | Clinical + FHIR standard input |
| Include BPMN in DocumentReferences linked to CarePlan activities via extension | FHIR extension design |
| Write CarePlan + associated resources back to HAPI FHIR server | — |
| Accept patient data as IPS instead of raw Bundle | Replace Phase 1 shortcut |

#### automation

| Work | Notes |
|---|---|
| Implement stub automation service that accepts BPMN from acp-writer | Receives BPMN over API |
| Define the BPMN contract in shared/ | — |

#### platform

| Work | Notes |
|---|---|
| Deploy agents via Kagenti on OpenShift (if selected) | Kagenti |
| OpenShell policies per agent (network, filesystem, credential scoping) | OpenShell |
| MCP Gateway for governed tool access | MCP Gateway |

#### Exit Criteria

- cpg-ingester is a multi-agent pipeline that extracts both DMN and recommendations
- acp-writer produces clinically meaningful CarePlans with recommendations
- Vector store operational with recommendation retrieval
- BPMN generated for automatable activities
- Automation service receives BPMN
- Agent identity and sandboxing via OpenShell/Kagenti

---

### Phase 4 — Governance + Safety + Evaluation

**Goal:** Add the governance stack that differentiates Red Hat AI. Quality gates, guardrails, evaluation.

#### All Areas

| Area | Work | Red Hat AI Tech |
|---|---|---|
| **platform** | NeMo Guardrails on agent I/O — healthcare-specific rules | NeMo Guardrails |
| **platform** | EvalHub — golden test sets per CPG, extraction fidelity scorers, plan quality scorers | EvalHub |
| **platform** | EvalHub gates that block deployment of degraded models/pipelines | EvalHub |
| **platform** | Garak red-teaming for healthcare-specific adversarial scenarios | Garak |
| **platform** | Agent identity via SPIFFE/SPIRE | SPIFFE/SPIRE |
| **platform** | Migrate from MaaS to Praxis (if available — expected Red Hat AI 3.6) | Praxis |
| **cpg-ingester** | Validation pipeline: compare extracted DMN against golden test cases | — |
| **acp-writer** | Validate CarePlan output against AI Transparency on FHIR IG | — |
| **acp-writer** | CarePlan quality scoring (automated + clinician review) | — |
| **automation** | Add BPMN execution engine or BPMN-to-Ansible converter | Ansible/SonataFlow |

#### Exit Criteria

- Guardrails actively filtering agent I/O
- EvalHub gates preventing degraded deployments
- Three audit trails: MLflow (tracing), OpenShell (sandbox), automation (execution)
- AI Transparency on FHIR compliance
- Praxis migration (if timeline allows)

---

### Phase 5 — UIs + Scale + Demo-Ready

**Goal:** Full user interfaces, multiple CPGs, polished demo for customers and field teams.

#### cpg-ingester UI

| Work | Notes |
|---|---|
| Upload CPG (PDF) | File upload interface |
| Confirm identified decisions and process/recommendations | Review + edit |
| Review DMN after conversion | Side-by-side with CPG source |
| Review recommendations before push to acp-writer | — |
| Interactive editing at each step | — |
| Push approved bundle (DMN + recommendations) to acp-writer | — |

#### acp-writer UI

| Work | Notes |
|---|---|
| Launchable via SMART on FHIR inside supporting EHR | SMART App Launch |
| Pull patient data as IPS from FHIR server for patient in context | — |
| Allow user to add notes about current situation | Free text input |
| Send all data to acp-writer server | API call |
| Review resulting care plan | CarePlan visualization |
| Visualize activity BPMN within care plan | BPMN renderer |
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
| AI Gateway for token rate limiting and cost showback | AI Gateway |

#### Exit Criteria

- Demo-ready system exercising 12+ Red Hat AI platform capabilities
- Full UIs for both cpg-ingester and acp-writer
- Mock-EHR launches acp-writer via SMART on FHIR
- 3-5 CPGs with multi-plan merging
- Presentation-ready materials

---

## Red Hat AI Technology Adoption Timeline

| Phase | Technologies Added |
|---|---|
| Phase 1 (complete) | Docling, LiteLLM (local), Drools/Kogito |
| Phase 2 | OpenShift, OpenShell, MaaS, vLLM, MLflow, MCP |
| Phase 3 | AutoRAG, Kagenti, MCP Gateway, vector store |
| Phase 4 | NeMo Guardrails, EvalHub, Garak, SPIFFE/SPIRE, Praxis |
| Phase 5 | AI Gateway, SMART on FHIR |

## Parallel Development Tracks

Each area can advance semi-independently within a phase. Cross-cutting dependencies are noted in the phase tables. The key synchronization points are:

1. **Agent framework selection (Phase 2 spike)** — blocks all multi-agent work in Phase 3
2. **OpenShift deployment (Phase 2)** — blocks OpenShell, MaaS, Kagenti
3. **Vector store + recommendation contract (Phase 3)** — blocks recommendation-backed care plans
4. **BPMN contract in shared/ (Phase 3)** — blocks automation service integration

Within each phase, a contributor can pick up any work item in their area without blocking others, as long as the phase's prerequisites are met.

## Open Spikes and Research Items

| Item | Phase | Notes |
|---|---|---|
| Agent framework evaluation | 2 | Compare Kagenti, LangGraph, CrewAI, Rookery, fips-agents |
| Praxis investigation | 2 | Red Hat AI 3.6 (Nov 2026). Successor to OGX/LlamaStack as AI gateway. Will replace MaaS when available. |
| Effective FHIR CarePlan goals | 3 | Research what makes clinically meaningful goals — clinical + FHIR standard input needed |
| AI Transparency on FHIR IG | 3 | HL7 STU1 ballot. Defines how to tag FHIR resources generated/influenced by AI |
| Recommendation contract format | 3 | No established standard (unlike DMN/BPMN/FHIR). Design needed. |
| BPMN-to-Ansible conversion | 4 | Feasibility and approach |
| SMART-EHR-Launcher (CSIRO) | 5 | Open-source EHR simulator for SMART app launch — evaluate for mock-EHR |
