# CPG-to-Actionable-Care-Plans on Red Hat AI: Project Proposal

This project is to provide a template of a multi-agent system that solves a complex, real-world problem on the Red Hat AI platform. Specifically it shows transforming Clinical Practice Guidelines into patient-specific, FHIR-compliant care plans. The pattern this represents, documentation to personalized, actionable business processes, is prevalent in healthcare and other industries.  

**Please note**: This project is intended to push the boundaries of the current technology. This means that it is being developed in a rapidly evolving ecosystem. **All technology** choices below are **subject to change**.

---

## 1\. Executive Summary

We propose building a **CPG-to-Actionable-Care-Plan demonstration system on Red Hat AI** that ingests Clinical Practice Guidelines (CPGs), extracts computable decision logic and narrative recommendations, integrates patient data, composes personalized care plans, and oversees their execution — all governed, traced, and evaluated by the platform's native capabilities.

The project exercises **every major Red Hat AI component** — from inference (vLLM) through governance (AI Gateway, MCP Gateway, OpenShell) to observability (MLflow, EvalHub) — in a single, cohesive, high-impact vertical. It demonstrates what the platform makes possible in a domain where correctness, auditability, and safety are non-negotiable.

**Why this project, why now:**

1. **Platform showcase.** No single demo today touches vLLM, MLflow, EvalHub, AI Gateway, MCP Gateway, OpenShell, TrustyAI, NeMo Guardrails, Auto-RAG, Docling, and Ansible in one system. This one does.  
2. **Working prototype exists.** A functionally complete prototype has already proven the hardest parts and was demonstrated at the HIMSS 26 conference. LLM-driven DMN extraction, MCP-based decision invocation, FHIR CarePlan generation with full provenance — across 5 CPGs and 27+ decision tables. The port to Red Hat AI adds enterprise governance, not research risk.  
3. **Healthcare is the right vertical.** Regulated, high-stakes, data-intensive — the exact environment where Red Hat AI's governance and observability capabilities are most differentiated. HCA Healthcare already runs SPOT (sepsis prediction) on OpenShift \+ Ansible across 160+ hospitals and 2.5M+ patients. This project extends that story from predictive AI into **agentic AI** — the frontier Red Hat AI 3.4 is built for.  
4. **Timing.** Red Hat AI 3.4 shipped the agent governance stack (MCP Gateway, OpenShell, SPIFFE/SPIRE identity, MLflow tracing). The CMS Prior Authorization Rule mandates FHIR-based APIs as of January 2026\. The market is ready; the platform is ready.

---

## 2\. The Problem

Clinical Practice Guidelines are published as narrative documents — PDFs, sometimes hundreds of pages — containing decision logic, recommendations, dosing tables, risk assessments, and care pathways. Today, translating a CPG into actionable care for a specific patient is a manual, error-prone, time-consuming process that depends on individual clinician recall and interpretation.

The gap between published evidence and bedside practice is well-documented:

- **17 years** — average time for research evidence to reach routine clinical practice.  
- **55%** — percentage of recommended care actually delivered in the US (RAND, McGlynn et al.).  
- **68%** — percentage of healthcare ML projects that fail in production (peer-reviewed MLOps study).  
- **Alert fatigue** — rule-based CDS systems generate so many false positives that clinicians routinely override them.

AI can bridge this gap — but only if the system is **auditable** (every decision traceable to its guideline source), **deterministic where it matters** (clinical decisions made by validated logic, not LLM inference), **governed** (sandbox execution, RBAC, policy gates), and **evaluated continuously** (not just tested once at deployment).

No off-the-shelf product solves this. The solution requires orchestrating multiple AI capabilities — document understanding, decision logic extraction, patient data integration, plan composition, execution governance — under a unified platform. That platform is Red Hat AI.

### Generalization

While this proposal focuses on the problem of CPGs to actionable care plans, the pattern is generally applicable. The process of taking documentation and turning it into actionable processes is prevalent across healthcare, but also across other industries. In healthcare, a similar challenge exists in the prior-authorization and claims adjudication space, in patient discharge, in admitting patients, and so on. Outside of healthcare, a similar pattern is valid anytime an organization wants to turn its Standard Operating Procedures into processes that can be personalized to individual cases. 

---

## 3\. What the System Does

Six steps, each mapping to Red Hat AI capabilities:

```
┌──────────────────────────────────────────────┐
│  OBSERVABILITY & EVAL     MLflow · EvalHub · RAGAS · Garak                  │
│  (across all steps)       Tracing · evaluation · prompt management          │
└──────────────────────────────────────────────┘
         ▲ OpenTelemetry traces / scores / feedback
┌──────────────────────────────────────────────┐
│  OPENSHELL SANDBOX        Kernel-enforced isolation across ALL steps        │
│  (across all steps)       Per-step network policy · filesystem restrictions │
│                           SHA-256 audit trail · per-binary access control   │
└──────────────────────────────────────────────┘
┌───────┐   ┌────────┐  ┌────────┐  ┌─────────────┐
│ 1. INGEST  │   │ 2. EXTRACT  │  │ 4. PATIENT   │  │ 5. COMPOSE PLAN     │
│   CPGs     │→ │   Decision  │  │   DATA       │→ │   Multi-agent       │
│ Docling +  │   │   Logic     │  │  HAPI FHIR   │  │   orchestration     │
│ pipeline   │   │ 3. EXTRACT  │  │  via MCP     │  │   (BYO framework)   │
│            │→ │   Narrative │→ │              │  │                     │
└───────┘   └────────┘  └─────────┘  └────┬───────┘
                                          			     │ tool calls
                        ┌──────────────────────────────────────┴─────┐
  ACTION                │ 6. OVERSEE EXECUTION                            │
  GOVERNANCE            │  Ansible playbooks · TrustyAI + NeMo guardrails │
                        │  OPA/Rego policy gate                           │
                        └────────────────────────────────────────────┘
```

### Step 1 — Ingest CPGs

Parse complex guideline PDFs — tables, flowcharts, multi-column layouts — into structured, machine-readable form.

| Role | Pluggable Options | Notes |
| :---- | :---- | :---- |
| Document parser | **Docling** (default), Unstructured.io,  marker-pdf | Docling: MIT, LF AI & Data, Granite-Docling-258M VLM, OpenShift Operator with Red Hat |
| Distributed processing | Ray Data on KubeRay | For high-volume guideline corpora |
| Pipeline orchestration | Kubeflow Pipelines (KFP) | Versioned, repeatable DAG |
| Storage | S3 / OpenShift Data Foundation | Raw docs \+ parsed output |

**Why Docling as the default:** Red Hat is co-developing the Docling OpenShift Operator with IBM, intends to include Docling as a supported RHEL AI feature, and calls it "the number one open source repository for document intelligence." 61K GitHub stars, MIT license, purpose-built for AI pipelines with native LangChain/LlamaIndex/CrewAI integrations.

**OpenShell sandbox:** CPG documents arrive from external sources — a compromised or malicious PDF could exploit the document parser. The Docling parsing process runs inside an OpenShell sandbox with Landlock filesystem restrictions (write only to object storage) and network namespace isolation (reach only the S3 endpoint — no access to FHIR, DMN engines, or external networks). A parser exploit cannot escalate beyond the ingestion boundary.

### Step 2 — Extract Computable Decision Logic

An LLM (vLLM-served) reads parsed guideline text and extracts operational logic into **DMN decision tables** — the reviewable, executable artifact at the center of the system.

| Role | Pluggable Options | Notes |
| :---- | :---- | :---- |
| LLM inference | **vLLM** (direct) or AI Gateway / Models-as-a-Service | Granite, validated catalog models |
| Decision format | **DMN** (primary), DRL for complex logic, PMML for predictive sub-decisions |  |
| Decision engine | **Drools DMN engine** (Apache KIE), Kogito decision services on Quarkus | DMN 1.1–1.4, conformance level 3 |
| Workflow orchestration | OpenShift Serverless Logic (SonataFlow) | For multi-step decision chains |
| Authoring / review | KIE DMN editor (VS Code / online / standalone) | Clinician sign-off surface |

**Why DMN:** The decision table *is the reviewable artifact*. A clinician can read, validate, and sign off on a graphical decision table without understanding code. This is the human-in-the-loop trust surface between guideline text and executable logic. The BPM+ Health community validates this approach with \~1,000 pre-built evidence-based clinical DMN/BPMN models. The existing prototype has already proven LLM-to-DMN extraction works across 5 CPGs and 27+ decision tables.

Each decision service exposes a REST endpoint, surfaced to agents as an MCP tool.

**OpenShell sandbox:** The extraction agent processes parsed guideline text that could contain prompt-injection attempts. Its sandbox permits network access only to vLLM and object storage — no access to FHIR (preventing unauthorized patient data retrieval) or Ansible (preventing premature action execution). If an injected instruction in the guideline text tries to redirect the agent to an external endpoint, the network namespace blocks it at the kernel level.

### Step 3 — Extract Non-Computable Recommendations

Not all guideline content reduces to decision tables. Narrative recommendations, contextual guidance, and clinical rationale become RAG-retrievable context.

| Role | Pluggable Options | Notes |
| :---- | :---- | :---- |
| Embeddings | vLLM / KServe | Shared inference infrastructure |
| Vector store | Milvus, PostgreSQL/pgvector, or other | pgvector reuses existing Postgres |
| RAG optimization | **Auto-RAG** (Red Hat AI 3.4) | Automates chunk size, embedding model, retrieval settings |
| Retrieval | Agent code, evaluated by RAGAS | Faithfulness-grounded context |

**Auto-RAG** (new in RHOAI 3.4, tech preview) automates RAG pipeline optimization — taking teams from raw dataset to high-performing pipeline in minutes instead of days. Grid search over parsing, chunking, query expansion, retrieval, and reranking strategies with leaderboard-based evaluation.

**OpenShell sandbox:** The embedding pipeline processes parsed guideline text and writes to the vector store. Its sandbox restricts network access to the embedding model endpoint and vector store only — no FHIR access, no action endpoints. Filesystem restrictions prevent the pipeline from reading or writing outside its designated storage paths.

**Note**: This step is subject to change as the design progresses. It is the subposition of this project that RAG is a reasonable solution here, but the existing demo uses an expert agent approach and other investigations have used knowledge graphs. 

### Step 4 — Ingest Patient Data

| Role | Pluggable Options | Notes |
| :---- | :---- | :---- |
| Clinical data | **HAPI FHIR** | System of record, HL7 FHIR R4, in-cluster for PHI residency |
| Agent access | **MCP tools** | FHIR queries surfaced as governed tool calls |
| Feature engineering | Feast (optional) | Engineered features for PMML/AutoML scoring |

HAPI FHIR is the clinical system of record. 98% of US hospitals now expose FHIR R4 APIs (ONC 21st Century Cures Act). Patient data is queried fresh for every plan — never cached in secondary stores.

**OpenShell sandbox:** This is the PHI boundary — the most security-critical step. The patient data retrieval process runs in a sandbox that permits network access **only** to HAPI FHIR. It cannot reach external networks, object storage containing other patients' data, or the internet. This enforces PHI containment at the kernel level — stronger than any application-layer access control. Even if a prompt injection compromises the agent's reasoning, the kernel-enforced network namespace prevents data exfiltration.

### Step 5 — Compose the Care Plan

A multi-agent system composes the patient-specific care plan by calling decision services (Step 2), retrieving recommendations (Step 3), and reading patient data (Step 4\) — all via MCP tool calls, all traced by MLflow, all governed by the AI Gateway.

| Role | Pluggable Options | Notes |
| :---- | :---- | :---- |
| Agent framework | **LangGraph**, CrewAI, AG2, or other | BYO — Red Hat AI is framework-agnostic |
| LLM inference | **vLLM** or AI Gateway / Models-as-a-Service | OpenAI-compatible API |
| Input safety | **TrustyAI Guardrails Orchestrator** | GA since RHOAI 3.0 |
| Output safety | **NeMo Guardrails** | GA in RHOAI 3.4 — conversation rails, PII detection, content filtering |
| Agent identity | **SPIFFE/SPIRE** | Cryptographic workload identity, least-privilege access |
| Tool governance | **MCP Gateway** | Auth, RBAC, tool-level access control |
| Traffic governance | **AI Gateway** | Token rate limiting, cost showback, tiered access |

**Red Hat's agent strategy is "Bring Your Own Agent" (BYOA).** The platform governs; it doesn't prescribe the framework. This means the agent framework is a pluggable slot — the choice of LangGraph vs. CrewAI vs. AG2 vs. BeeAI is an implementation decision, not an architectural one. What matters is that all tool calls flow through MCP, all inference flows through the AI Gateway, and all execution is traced by MLflow.

**OpenShell sandbox:** The plan composition agent has the broadest tool access in the system — DMN services, FHIR, RAG, potentially memory — making it the highest-risk process. OpenShell enables **least-privilege per sub-agent**: the FHIR query sub-agent can reach only HAPI FHIR; the DMN invocation sub-agent can reach only Kogito services; the RAG retrieval sub-agent can reach only the vector store. No single sub-agent gets access to everything. Per-binary policy enforcement means OpenShell knows *which binary inside the sandbox* is making each request (verified by SHA-256 hash) and enforces different rules for each one — so `python` running the FHIR query module can reach the FHIR server, but a subprocess spawned by a prompt injection cannot.

### Step 6 — Oversee Execution

Ansible governs what happens when care plan activities fire in the real world.

**Ansible governs the actions.** Care-plan activities (schedule OR, notify vendor, order pre-op labs, reschedule) are **pre-approved Ansible playbooks**. The agent *selects* a playbook; it never improvises the action. AAP MCP server (GA) inherits RBAC. **Event-Driven Ansible** drives the next step from clinical events (lab posted, appointment cancelled).

**OpenShell sandbox:** The execution step gets the tightest sandbox. The agent process that triggers Ansible playbooks can reach only the AAP API endpoint — not FHIR, not the internet, not other agents. Combined with Ansible's RBAC and OPA/Rego policy gates, this creates the narrowest possible blast radius for real-world actions.

**Three independent control points across the full pipeline:** DMN/Drools constrains *what's clinically valid* → Ansible constrains *what can fire* → OpenShell constrains *what every process can reach at every step*.

---

## 4\. Pluggable Architecture — Swap Any Layer

A core design principle: **the platform is the constant; everything else is a pluggable slot.** Every non-platform component connects through a standard interface (MCP, REST, OpenTelemetry) and can be swapped without redesigning the system.

```
┌─────────────────────────────────────┐
│                    RED HAT AI PLATFORM                       │
│  (vLLM · AI Gateway · MCP Gateway · MLflow · EvalHub ·       │
│   OpenShell · TrustyAI · NeMo Guardrails · SPIFFE/SPIRE)     │
│                                                              │
│   These are the constants. Everything below is pluggable.    │
└───────────────┬─────────────────────┘
                           │ standard interfaces
    ┌─────────────┼─────────────┐
    │                      │                      │
┌──┴──────┐  ┌───┴─────┐  ┌─────┴───────┐
│ DOCUMENT      │  │ DECISION      │  │ AGENT FRAMEWORK      │
│ INGESTION     │  │ ENGINE        │  │                      │
│               │  │               │  │ • LangGraph          │
│ • Docling     │  │ • Drools/DMN  │  │ • CrewAI             │
│ • Unstructured│  │ • CQL engine  │  │ • AG2                │
│ • marker-pdf  │  │ • custom      │  │ • BeeAI              │
│ • other       │  │               │  │ • other              │
└─────────┘  └─────────┘  └─────────────┘

┌─────────┐  ┌─────────┐  ┌──────────────┐
│ VECTOR STORE  │  │ CLINICAL DATA │  │ MEMORY (optional)    │
│               │  │               │  │                      │
│ • Milvus      │  │ • HAPI FHIR   │  │ • Zep / Graphiti     │
│ • pgvector    │  │ • other FHIR  │  │ • Cognee             │
│ • other       │  │   server      │  │ • Mem0               │
│               │  │               │  │ • framework-native   │
└─────────┘  └─────────┘  │ • none               │
                                         └─────────────┘
```

**The memory layer is entirely optional.** It adds statefulness across encounters (clinician workflow preferences, process continuity, institutional patterns) but is not required for the core pipeline. If included, it holds **non-clinical context only** — clinical facts of record stay in FHIR, queried fresh. Any memory solution (Zep/Graphiti, Cognee, Mem0, framework-native checkpointing, or none at all) plugs in as an MCP tool and inherits the platform's governance, sandboxing, and tracing automatically.

**What makes swapping safe:** every pluggable component connects through one of three standard interfaces — **MCP** (tool calls), **REST** (services), or **OpenTelemetry** (observability). As long as the replacement speaks the interface, the rest of the system doesn't change.

---

## 5\. Red Hat AI 3.4 Platform Coverage

This project exercises nearly every major capability shipped in Red Hat AI 3.4:

| Platform Capability | Status | How This Project Uses It |
| :---- | :---- | :---- |
| **vLLM / KServe** | GA | LLM inference for extraction, plan composition, RAG embeddings |
| **AI Gateway (Models-as-a-Service)** | GA | Centralized routing, token rate limiting, cost showback |
| **MLflow** | GA (3.4) | End-to-end tracing of every agent step, tool call, and decision |
| **NeMo Guardrails** | GA (3.4) | Conversation rails, PII detection, content filtering on agent I/O |
| **TrustyAI Guardrails Orchestrator** | GA (3.0+) | Inference-boundary safety coordination |
| **MCP Gateway** | Tech Preview | Governed tool access — FHIR, DMN, Ansible, memory all via MCP |
| **EvalHub** | Tech Preview | Extraction fidelity scoring, plan quality evaluation, red-teaming |
| **Auto-RAG** | Tech Preview | Automated optimization of the recommendation retrieval pipeline |
| **OpenShell** | Early Validation | Kernel-enforced sandbox across **all steps** — per-step network policy, PHI containment, prompt-injection defense, SHA-256 audit trail |
| **SPIFFE/SPIRE** | New | Cryptographic agent identity, least-privilege access |
| **Docling** (partner) | Supported | CPG document parsing with Granite-Docling-258M |
| **Ansible Automation Platform** | GA | Pre-approved care plan activity execution via playbooks |
| **Event-Driven Ansible** | GA | Reactive workflow triggered by clinical events |
| **Automated Red Teaming** (Garak) | New | Adversarial safety testing in CI/CD |

**12+ platform capabilities exercised by one project.** No other single demonstration achieves this breadth of coverage.

---

## 6\. Alignment with Red Hat's Strategic Goals

### 6.1 — "From inference to agents"

Red Hat AI 3.4's tagline is "From inference to agents." The Q2 2026 What's New session organizes the entire platform around three enterprise AI challenges: **Cost** (running AI), **Control** (governing AI), and **Complexity** (simplifying AI). This project addresses all three:

- **Cost:** vLLM serves inference across all six steps on any hardware (CPU, NVIDIA, AMD, Intel). The AI Gateway provides cost showback and tiered access.  
- **Control:** MCP Gateway governs every tool call. OpenShell sandboxes every process at every step — from document ingestion through plan execution — with per-step network policies that enforce least-privilege at the kernel level. Ansible constrains every real-world action. MLflow traces everything. Three independent audit layers: *why* the agent decided (MLflow), *what touched what* (OpenShell), *what executed* (Ansible).  
- **Complexity:** Auto-RAG automates the recommendation pipeline. EvalHub benchmarks extraction quality and plan quality with healthcare-specific test suites out of the box. Docling handles document ingestion. The agent framework is BYO.

### 6.2 — Agentic AI governance (the differentiated story)

Every cloud provider offers LLM inference. Red Hat AI's differentiation is the governance stack for **agentic AI** — systems where autonomous agents make decisions, call tools, and trigger real-world actions. This project is a purpose-built showcase for that governance stack:

- **Agent identity** (SPIFFE/SPIRE) — every agent has a cryptographic identity  
- **Tool governance** (MCP Gateway) — every tool call is authenticated and authorized  
- **Runtime sandboxing** (OpenShell) — every process at every step is kernel-constrained with per-step network policy  
- **Action governance** (Ansible) — every real-world action is a pre-approved playbook  
- **Decision governance** (DMN) — every clinical decision is deterministic and reviewable  
- **Full-stack tracing** (MLflow) — every step is observable and evaluatable

Healthcare is the ideal vertical to demonstrate this because the consequences of ungoverned agent actions are tangible and severe.

### 6.3 — OpenShell as defense-in-depth (not just execution sandboxing)

Most agent sandbox approaches apply isolation only at the final execution step. This project demonstrates **OpenShell across the full pipeline** — a defense-in-depth model where every step runs under a tailored, kernel-enforced security policy:

| Step | OpenShell Policy | Threat Mitigated |
| :---- | :---- | :---- |
| **1\. Ingest** | Parser can write only to object storage; no network beyond S3 | Malicious document exploits the parser → lateral movement blocked |
| **2\. Extract logic** | Agent reaches only vLLM and storage; no FHIR, no Ansible | Prompt injection in guideline text → cannot access patient data or trigger actions |
| **3\. RAG/embeddings** | Pipeline reaches only embedding model \+ vector store | Injection in parsed text → cannot exfiltrate data |
| **4\. Patient data** | Process reaches only HAPI FHIR — nothing else | PHI containment enforced at kernel level, not application level |
| **5\. Compose plan** | Per-sub-agent policies — FHIR agent reaches FHIR, DMN agent reaches Kogito, RAG agent reaches vector store | Least-privilege per sub-agent; no single process gets access to everything |
| **6\. Execute** | Execution agent reaches only the AAP API endpoint | Blast radius of real-world actions narrowed to pre-approved playbooks |

This is a strong differentiator for two reasons:

1. **It's a showcase for OpenShell's per-binary policy enforcement** — the feature that distinguishes OpenShell from container-level isolation. OpenShell knows *which binary* inside the sandbox is making each request (verified by SHA-256 hash) and enforces different rules for each one. This project demonstrates that capability across six distinct security contexts in one system.

2. **Healthcare makes the story visceral.** "The document parser can't reach patient data" and "a prompt injection can't trigger a medication order" are concrete, auditable claims that resonate with compliance officers and CISOs — not abstract security properties.

Red Hat and NVIDIA are co-developing OpenShell. This project gives it a production-representative proving ground in the highest-stakes vertical.

### 6.5 — Healthcare vertical traction

Red Hat already has healthcare credibility:

- **HCA Healthcare** runs SPOT (sepsis prediction) on OpenShift \+ Ansible \+ Kafka across **160+ hospitals and 2.5M+ patients** — detecting sepsis 20 hours earlier.  
- **Boston Children's Hospital** runs ChRIS (medical imaging) on OpenShift.  
- **Clalit Health Services** (Israel's largest health service) uses OpenShift AI for clinical research models.	  
- **EvalHub ships with healthcare-specific test suites** out of the box.  
- **CMS Prior Authorization Rule** mandates FHIR-based APIs as of January 2026 — regulatory tailwind for FHIR-native solutions.

This project extends the healthcare story from **predictive AI** (SPOT) into **agentic AI** — the frontier that Red Hat AI 3.4 is purpose-built for.

### 6.6 — Red Hat \+ NVIDIA joint value

The project demonstrates the **Red Hat AI Factory with NVIDIA** joint solution:

- **vLLM** inference across NVIDIA GPUs (including Blackwell support)  
- **OpenShell** (Red Hat \+ NVIDIA co-development) for sandbox execution  
- **NeMo Guardrails** (NVIDIA) for agent safety  
- **Confidential computing** option for PHI processing with hardware attestation

### 6.7 — Open source, model-agnostic, no lock-in

Every component in the architecture is open source and model-agnostic. The system runs on open models served by vLLM. The agent framework is BYO. The vector store, decision engine, and memory layer are all pluggable. This is the Red Hat value proposition applied to AI: **enterprise-grade governance for open, composable systems.**

---

## 7\. What the Prototype Already Proves

The existing prototype, demonstrated at HIMSS 26, has already validated the most technically uncertain parts of the system:

| Capability | Status | Evidence |
| :---- | :---- | :---- |
| LLM extraction of CPG → DMN decision tables | Working | 5 CPGs, 27+ DMN tables, FEEL expressions validated |
| DMN deployment and MCP-based invocation | Working | All tables deployed, callable as MCP tools |
| Deterministic clinical decisions via DMN engine | Working | Server-side execution, instance-stamped, traceable |
| FHIR CarePlan generation with provenance | Working | Transaction Bundles with Goal, Activity, Provenance, AI Device |
| Multi-CPG care plan merging | Working | 4 plans combined with conflict detection and resolution |
| AI transparency (HL7 AI Transparency IG) | Working | AIAST security labels, provenance chain, CPG citations |
| Clinical code verification (SNOMED, LOINC, ICD) | Working | No hallucinated codes in output |

**The prototype de-risks the clinical logic. The Red Hat AI port adds what the prototype lacks:** enterprise governance (OpenShell, MCP Gateway, Ansible), observability (MLflow, EvalHub), safety (TrustyAI, NeMo Guardrails), evaluation (EvalHub with healthcare suites, RAGAS, Garak), and scalable inference (vLLM, AI Gateway).

The port replaces:

- Claude Code agent skills → BYO agent framework on vLLM-served models  
- Trisotech (commercial) → Drools/Kogito DMN engine (Apache KIE, open source)  
- Manual observation → MLflow tracing \+ EvalHub evaluation  
- No sandbox → OpenShell kernel-enforced security  
- No evaluation gate → EvalHub as promotion gate in CI/CD

---

## 8\. Feedback Loops — How the System Improves

The system improves through multiple loops at different cadences. MLflow is the connective tissue — its traces are the raw material for most of them.

| Loop | Cadence | Mechanism |
| :---- | :---- | :---- |
| **Guardrails** | Sub-second | TrustyAI/NeMo screen every agent I/O |
| **Retrieval self-grade** | Per-turn | Agentic RAG re-queries on low confidence |
| **Memory adaptation** (if enabled) | Per-turn | Clinician override → preference update → immediate adaptation |
| **Clinician review** | Per-plan | Accept/edit/reject → MLflow feedback |
| **Plan quality eval** | Per-change | MLflow scorers → prompt optimization → redeploy |
| **Extraction fidelity** | CI/CD | EvalHub scores DMN extraction vs golden set → improve prompt/model |
| **RAG tuning** | CI/CD | RAGAS faithfulness → tune chunking/embeddings → re-index |
| **Safety/red-team** | CI/CD | Garak adversarial scans → update guardrail rules |
| **Outcome** | Weeks–months | Plan execution outcomes via FHIR → refine decision logic |
| **Guideline update** | Per CPG release | New CPG version → re-extract → diff → re-review → version bump |

These loops feed different mechanisms by timescale — *guardrails/memory* (fast/online), *prompts \+ eval* (medium/offline), *decision logic \+ models* (slow/clinical). They are complementary, not redundant.

---

## 9\. What Must Be Built vs. What Exists

| Layer | Exists (platform/ecosystem) | Must Be Built |
| :---- | :---- | :---- |
| Document parsing | Docling, OpenShift Operator | CPG-specific parsing pipeline (KFP DAG) |
| LLM inference | vLLM, AI Gateway | Extraction prompts, plan composition prompts |
| Decision engine | Drools/Kogito (Apache KIE) | DMN extraction pipeline, clinician review workflow |
| RAG pipeline | Auto-RAG, vector stores | Guideline-specific chunking/indexing strategy |
| Patient data | HAPI FHIR, MCP tools | FHIR-to-agent query mapping |
| Agent orchestration | BYO framework, MCP Gateway | Agent logic, tool call composition, plan assembly |
| Execution governance | OpenShell, Ansible, OPA/Rego | Playbook library for care plan activities |
| Observability | MLflow, EvalHub | Custom scorers (guideline adherence, plan quality) |
| Safety | TrustyAI, NeMo, Garak | Healthcare-specific guardrail rules, red-team scenarios |
| Evaluation | EvalHub, healthcare suites | Golden-set test cases per CPG, vignette regression tests |

The platform provides the infrastructure. The project builds the healthcare-specific content and integration logic on top of it.

---

## 10\. Risk Assessment

| Risk | Mitigation |
| :---- | :---- |
| **DMN extraction fidelity** — LLM-generated decision tables may not faithfully represent the guideline | Build a CPG↔DMN validation loopback: rule-to-source traceability, coverage reports, vignette regression tests, clinician sign-off artifact.  |
| **OpenShell maturity** — early validation, not yet productized | The demo can run without OpenShell initially; add it as the integration matures. The sandbox is an additive governance layer, not a prerequisite. |
| **EvalHub maturity** — tech preview | Use MLflow (GA) as the primary observability layer; EvalHub adds evaluation on top. Both are complementary. |
| **MCP Gateway maturity** — tech preview | Direct MCP connections work today; the gateway adds governance. The architecture works with or without the gateway. |
| **PHI handling** — patient data requires HIPAA controls | All inference runs in-cluster. No PHI leaves the OpenShift environment. Confidential containers (NVIDIA H100 \+ CoCo) available for hardware-attested isolation. Demo can use synthetic patient data. |
| **Clinical validation** — AI-generated care plans require clinical review | Human approval gates on all plans. The system proposes; clinicians approve. Ansible blast radius is controlled by playbook pre-approval and RBAC. |

---

## 11\. Recommended Approach

### Phase 1 — Validate

Port one CPG to the Red Hat AI stack:

- vLLM inference for extraction and plan composition  
- Drools/Kogito DMN engine replacing Trisotech  
- MLflow tracing of the full pipeline  
- Basic MCP tool integration (FHIR, DMN)  
- Build the CPG↔DMN validation loopback (vignette regression tests)

**Exit criteria:** One CPG end-to-end on Red Hat AI, with DMN extraction verified against golden test cases and the full pipeline traced in MLflow.

### Phase 2 — Govern 

Add the governance and safety layers:

- OpenShell sandbox for agent execution  
- MCP Gateway for tool governance  
- NeMo Guardrails \+ TrustyAI on agent I/O  
- Ansible playbooks for care plan activity execution  
- EvalHub evaluation gate in CI/CD (Garak red-teaming, custom healthcare scorers)

**Exit criteria:** Three independent audit trails (MLflow, OpenShell, Ansible). EvalHub gates deployment promotion.

### Phase 3 — Scale 

Expand to multiple CPGs and demonstrate the full vision:

- 3–5 CPGs with multi-plan merging  
- Auto-RAG for recommendation retrieval optimization  
- Docling ingestion pipeline with KFP orchestration  
- AI Gateway with cost showback and tiered access  
- Optional: memory layer for clinician preferences  
- Demo-ready presentation with synthetic patient data

**Exit criteria:** Multi-CPG demonstration exercising 12+ platform capabilities. Demo-ready for customers and field teams.

---

## 12\. Conclusion

This project is a rare opportunity to build a single demonstration that:

1. **Exercises the full Red Hat AI platform** — not a toy example of one feature, but a production-representative system that touches every major capability.  
2. **Tells a compelling story** in a high-stakes vertical where governance, auditability, and safety are existential requirements — not nice-to-haves.  
3. **Builds on proven work** — the prototype has already validated the hardest technical risks.  
4. **Advances Red Hat's strategic narrative** from inference to agentic AI, from predictive healthcare AI (SPOT) to governed autonomous clinical agents.  
5. **Demonstrates the Red Hat value proposition** — open source, model-agnostic, pluggable components, enterprise governance. No lock-in at any layer.

The platform is ready. The prototype is ready. The market is ready.

