# CPG to Actionable Care Plans

> **Note:** This project is just starting. None of the code in this repo is finalized. Treat it all as experimental and expect volatile and frequent changes. 

A multi-agent system that transforms Clinical Practice Guidelines (CPGs) into patient-specific, FHIR-compliant, actionable care plans — built on the Red Hat AI platform.

CPGs are published as narrative documents (PDFs, sometimes hundreds of pages) containing decision logic, recommendations, dosing tables, risk assessments, and care pathways. Today, translating a CPG into actionable care for a specific patient is manual, error-prone, and depends on individual clinician recall. This project bridges that gap with AI while keeping clinical decisions deterministic, auditable, and governed.

## Architecture

The system has four application components connected by standards-based contracts, plus shared platform services:

```
  CPG (PDF)
      │
      ▼
┌─────────────┐   DMN    ┌─────────────┐   FHIR CarePlan   ┌──────────┐
│ cpg-ingester │ ───────► │  acp-writer  │ ────────────────► │ mock-EHR │
│              │  Recs*   │              │                   └──────────┘
│              │ ───────► │  (Drools /   │   BPMN
└─────────────┘          │   Kogito)    │ ────────────────► ┌────────────┐
                         └─────────────┘                   │ automation  │
                               ▲                           └────────────┘
                               │
                          Patient Data
                           (FHIR IPS)

  * Contract format TBD — see Open Questions
```

**Standards as contracts:** DMN is the interface between `cpg-ingester` and `acp-writer` for decision logic. FHIR is the interface for patient data and care plans. BPMN is the interface between `acp-writer` and `automation`. Each component is pluggable behind its standard — swap the runtime without changing the producer. The contract for recommendations (cpg-ingester to acp-writer's vector store) is an open question — no established standard exists for this boundary.

## Components

| Directory | Purpose |
|---|---|
| [`cpg-ingester/`](cpg-ingester/) | Parses CPG documents (via Docling) and produces two outputs: (1) DMN decision tables for computable logic, and (2) recommendations and other non-computable content for the acp-writer's vector store. |
| [`acp-writer/`](acp-writer/) | Composes patient-specific care plans by invoking DMN decision services (Drools/Kogito), retrieving recommendations from its vector store, and integrating patient data from FHIR. Outputs FHIR CarePlans and BPMN for automatable activities. The decision engine and vector store are internal implementation details. Includes the clinician review UI (SMART on FHIR). |
| [`automation/`](automation/) | Executes BPMN process definitions produced by the acp-writer. The runtime is pluggable — Ansible playbooks, SonataFlow, or any BPMN-conformant engine. |
| [`mock-EHR/`](mock-EHR/) | HAPI FHIR server acting as an EHR proxy, plus a simple EHR client that the acp-writer can launch within. Used for development and demonstration. |
| [`platform/`](platform/) | Shared infrastructure services (MaaS, MLflow) consumed by multiple application components. On OpenShift AI these are platform capabilities; for local dev this directory provides equivalent deployments. |
| [`shared/`](shared/) | Shared contracts and utilities across components. Used sparingly to prevent coupling. |
| [`dev_docs/`](dev_docs/) | Project proposals, design documents, and onboarding materials. Point-in-time references — may not reflect current state. |

## Pipeline Overview

1. **Ingest CPGs** — Parse complex guideline PDFs into structured, machine-readable form (Docling).
2. **Extract Decision Logic** — LLM extracts operational logic into DMN decision tables — the reviewable, executable artifact at the center of the system.
3. **Extract Recommendations** — Narrative recommendations and clinical rationale become RAG-retrievable context.
4. **Ingest Patient Data** — Query patient data from FHIR (IPS format), fresh for every plan.
5. **Compose Care Plan** — Multi-agent system invokes decision services, retrieves recommendations, and assembles a patient-specific FHIR CarePlan with provenance. Produces BPMN for automatable activities.
6. **Execute Automations** — BPMN process definitions drive care plan activities through pre-approved automation pathways.

## Key Design Principles

- **Deterministic where it matters.** Clinical decisions are made by validated DMN logic executed in a rules engine, not by LLM inference.
- **Standards-based contracts.** DMN, BPMN, and FHIR at every component boundary. Swap any runtime without changing its neighbors.
- **Auditable end-to-end.** Every decision traceable to its guideline source. Full provenance chain in FHIR output.
- **Human-in-the-loop.** Clinicians review and approve DMN tables (extraction) and care plans (composition). The system proposes; clinicians approve.
- **Pluggable architecture.** The platform is the constant; document parsers, decision engines, agent frameworks, vector stores, and automation runtimes are all swappable.

## Getting Started

This walks through the full pipeline: CPG PDF → parse → extract DMN → deploy decisions → generate care plan.

### Prerequisites

- [Podman](https://podman.io/) (preferred) or Docker with compose support
- Python 3.11+
- Google Cloud credentials with access to Claude on Vertex AI (for LLM-driven extraction)

### 1. Configure credentials

```bash
cp platform/litellm/deploy/.env.example platform/litellm/deploy/.env
# Edit .env with your Vertex AI project ID and location
# Ensure GCP Application Default Credentials are set up:
gcloud auth application-default login
```

### 2. Start infrastructure services

```bash
podman-compose up -d kogito litellm acp-writer   # or: docker compose up -d ...
# Wait for services
curl -sf http://localhost:8081/q/health/ready > /dev/null && echo "Kogito ready"
curl -sf http://localhost:8082/health/ready > /dev/null && echo "ACP Writer ready"
```

### 3. Parse a CPG with Docling

```bash
cd cpg-ingester
python3 -m venv .venv && source .venv/bin/activate
pip install -e . -e ../shared

# Parse the synthetic hypertension CPG
cpg-parse data/synthetic-hypertension-cpg.pdf -o output
# Produces: output/synthetic-hypertension-cpg.md
```

### 4. Extract DMN decision tables and deploy to acp-writer

```bash
# Extract DMN from the parsed CPG using the LLM, then deploy to acp-writer
cpg-extract-dmn output/synthetic-hypertension-cpg.md -o output \
  --deploy --acp-writer-url http://localhost:8082

# Or extract and deploy as separate steps:
cpg-extract-dmn output/synthetic-hypertension-cpg.md -o output
cpg-deploy-dmn output/decision-table-1.dmn output/decision-table-2.dmn \
  --acp-writer-url http://localhost:8082
```

Verify the models are deployed:
```bash
curl -sf http://localhost:8082/api/v1/decisions/models | python3 -m json.tool
```

### 5. Generate a care plan

Post patient data (FHIR Bundle) to the acp-writer API:
```bash
# Patient with hypertension + diabetes → medication path
curl -X POST http://localhost:8082/api/v1/careplans \
  -H "Content-Type: application/fhir+json" \
  -d @mock-EHR/data/patient-bundle-medication.json | python3 -m json.tool

# Patient with mild hypertension only → lifestyle path
curl -X POST http://localhost:8082/api/v1/careplans \
  -H "Content-Type: application/fhir+json" \
  -d @mock-EHR/data/patient-bundle-lifestyle.json | python3 -m json.tool
```

### 6. Tear down

```bash
podman-compose down   # or: docker compose down
```

### What each step exercises

| Step | Component | Red Hat AI tech |
|---|---|---|
| Parse CPG | cpg-ingester | Docling |
| Extract DMN | cpg-ingester | LLM via LiteLLM (Opus 4.6 on Vertex AI) |
| Deploy DMN | cpg-ingester → acp-writer API | — |
| Generate CarePlan | acp-writer → decision-service (JIT) | Drools/Kogito |

## Open Questions

- **Recommendation contract format.** The contract between `cpg-ingester` and `acp-writer` for non-computable recommendations has no established standard (unlike DMN for decisions, BPMN for processes, and FHIR for clinical data). Defining this interface is an open design question.

## License

This project is licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).
