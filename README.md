# CPG to Actionable Care Plans

A multi-agent system that transforms Clinical Practice Guidelines (CPGs) into patient-specific, FHIR-compliant, actionable care plans — built on the Red Hat AI platform.

CPGs are published as narrative documents (PDFs, sometimes hundreds of pages) containing decision logic, recommendations, dosing tables, risk assessments, and care pathways. Today, translating a CPG into actionable care for a specific patient is manual, error-prone, and depends on individual clinician recall. This project bridges that gap with AI while keeping clinical decisions deterministic, auditable, and governed.

## Architecture

The system has four main components connected by standards-based contracts:

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
| [`acp-writer/`](acp-writer/) | Composes patient-specific care plans by invoking DMN decision services (Drools/Kogito), retrieving recommendations, and integrating patient data from FHIR. Outputs FHIR CarePlans and BPMN for automatable activities. Includes the clinician review UI (SMART on FHIR). |
| [`automation/`](automation/) | Executes BPMN process definitions produced by the acp-writer. The runtime is pluggable — Ansible playbooks, SonataFlow, or any BPMN-conformant engine. |
| [`mock-EHR/`](mock-EHR/) | HAPI FHIR server acting as an EHR proxy, plus a simple EHR client that the acp-writer can launch within. Used for development and demonstration. |
| [`shared/`](shared/) | Shared resources and contracts across components. Used sparingly to prevent coupling. |
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

## Open Questions

- **Recommendation contract format.** The contract between `cpg-ingester` and `acp-writer` for non-computable recommendations has no established standard (unlike DMN for decisions, BPMN for processes, and FHIR for clinical data). Defining this interface is an open design question.

## License

This project is licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).
