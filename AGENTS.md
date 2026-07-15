# AGENTS.md

Rules, conventions, and architectural boundaries for AI coding agents working in this repository.

## Project Overview

This is a multi-agent system that transforms Clinical Practice Guidelines (CPGs) into patient-specific, FHIR-compliant, actionable care plans on the Red Hat AI platform. See [`dev_docs/`](dev_docs/) for the full project proposal and architecture slides.

## Repository Structure

```
cpg-to-acp/
├── cpg-ingester/    # Steps 1-3: Parse CPGs, extract DMN decision logic, extract recommendations
├── acp-writer/      # Steps 4-5: Patient data integration, care plan composition, clinician review UI
├── automation/      # Step 6: Execute BPMN process definitions produced by acp-writer
├── mock-EHR/        # HAPI FHIR server + simple EHR client (dev/test infrastructure)
├── platform/        # Shared infrastructure services (MaaS, MLflow)
├── shared/          # Cross-component contracts and utilities (use sparingly)
└── dev_docs/        # Project proposals, design docs (point-in-time references)
```

## Architectural Boundaries

These are hard rules. Do not violate them.

### Component Ownership

- **`cpg-ingester`** has two outputs: (1) DMN decision tables for computable logic, and (2) recommendations and other non-computable content destined for a vector store in `acp-writer`. It must not be coupled to the decision engine runtime or vector store implementation. It interacts with downstream services only through API/MCP. **Open issue:** The contract format for the recommendation/vector-store output is TBD — there is no established standard equivalent to DMN, BPMN, or FHIR for this boundary.
- **`acp-writer`** owns the Drools/Kogito decision engine runtime and the vector store. Both are internal implementation details of `acp-writer` — they are not platform services. It deploys and executes DMN. It produces two outputs: FHIR CarePlans (to the FHIR server) and BPMN (to automation).
- **`automation`** is a downstream runtime service that executes BPMN process definitions. It does not orchestrate other services.
- **`mock-EHR`** is development/test infrastructure. It is not application logic.
- **`platform`** holds shared infrastructure services (MaaS, MLflow) that multiple application components consume. These are platform-level dependencies, not application logic. On OpenShift AI, these are typically configured rather than deployed; for local dev, this directory contains the deployment artifacts.
- **`shared`** holds cross-component contracts and utilities. Use it sparingly to prevent coupling between components.

### Standards as Contracts

Each component boundary uses a standards-based contract:

| Boundary | Standard | Producer | Consumer |
|---|---|---|---|
| Decision logic | **DMN** | cpg-ingester | acp-writer |
| Recommendations | **TBD** | cpg-ingester | acp-writer (vector store) |
| Patient data | **FHIR** (IPS) | mock-EHR | acp-writer |
| Care plans | **FHIR** (CarePlan) | acp-writer | mock-EHR |
| Process automation | **BPMN** | acp-writer | automation |

Producers must not assume a specific consumer runtime. Consumers are pluggable behind the standard.

### Deployment

- Each component owns its own deployment artifacts (Dockerfiles, manifests, Helm charts, etc.).
- A root-level deployment file (e.g., docker-compose) is allowed only as a thin wrapper that references component-level deployments.

## Development Rules

### Code Quality
- Do not introduce security vulnerabilities (OWASP top 10). This project handles clinical data.
- Keep components independent. Avoid adding cross-component dependencies unless the contract goes through `shared/`.
- Prefer standard interfaces (MCP, REST, FHIR, DMN, BPMN) over proprietary integrations.

### Documentation
- `dev_docs/` contains point-in-time design documents. They may not reflect current state — always verify against the code.
- Each component has its own README describing its purpose, setup, and usage.

## Technology Context

Key technologies referenced in this project (all subject to change):

- **Document parsing:** Docling
- **Decision engine:** Drools / Kogito (Apache KIE), DMN format
- **FHIR server:** HAPI FHIR
- **Agent framework:** TBD / OpenShell
- **LLM inference:** vLLM, MaaS
- **Process automation:** Pluggable (Ansible, SonataFlow, BPMN engine)
- **Vector store:** Pluggable (Milvus, pgvector, etc.)
- **Platform:** Red Hat AI (OpenShift) with OpenShell

## License

Apache License, Version 2.0
