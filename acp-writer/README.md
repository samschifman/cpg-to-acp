# Actionable Care Plan Writer

This is the heart of the project. It composes patient-specific, FHIR-compliant care plans by combining clinical decision logic with patient data.

## Architecture

The acp-writer contains two sub-components:

- **`decision-service/`** — Java/Quarkus application (Apache KIE 10.2 / Kogito) that exposes DMN decision tables as REST endpoints. This is the Drools decision engine runtime.
- **`src/acp_writer/`** — Python service that orchestrates the care plan composition pipeline: accepts patient data, invokes the decision service, and assembles a FHIR CarePlan Bundle.

Both the decision engine and the vector store (Phase 2) are internal implementation details of acp-writer, hidden behind the API.

## Two Outputs

1. **FHIR CarePlan** — Patient-specific care plan with goals, activities (MedicationRequests, ServiceRequests), and references back to the patient record.
2. **BPMN** (Phase 3) — Process definitions for automatable care plan activities, sent to the automation service.

## API Contract

The acp-writer exposes a REST API defined in [`api/openapi.yaml`](api/openapi.yaml) and MCP tool definitions in [`api/mcp-tools.json`](api/mcp-tools.json).

**Design principles:**
- **Callers provide patient data directly** — the acp-writer does not query FHIR servers. Patient data is POSTed as a FHIR Bundle or IPS document.
- **Internal services are hidden** — Kogito and the vector store are behind the API. Callers deploy DMN and ingest knowledge; the API handles the rest.

### API Groups

| Group | Endpoints | Purpose |
|---|---|---|
| **Decisions** | `/api/v1/decisions/models`, `.../evaluate/{id}` | Deploy, list, remove, and evaluate DMN decision models |
| **Knowledge** | `/api/v1/knowledge/documents`, `.../search` | Ingest, list, remove, and search clinical recommendations |
| **Care Plans** | `/api/v1/careplans`, `.../status` | Generate, retrieve, list, and approve/reject care plans |
| **Health** | `/health`, `/health/ready`, `/api/v1/status` | Liveness, readiness, and component status |

### MCP Tools

Each REST endpoint has a corresponding MCP tool definition for agent framework integration:

| MCP Tool | REST Endpoint | Description |
|---|---|---|
| `deploy_decision_model` | `POST /api/v1/decisions/models` | Deploy DMN to the decision engine |
| `list_decision_models` | `GET /api/v1/decisions/models` | List deployed models |
| `evaluate_decision` | `POST /api/v1/decisions/evaluate/{id}` | Test a model with inputs |
| `ingest_knowledge` | `POST /api/v1/knowledge/documents` | Add content to the knowledge base |
| `search_knowledge` | `POST /api/v1/knowledge/search` | Search the knowledge base |
| `generate_careplan` | `POST /api/v1/careplans` | Generate a care plan from patient data |
| `get_careplan` | `GET /api/v1/careplans/{id}` | Retrieve a generated care plan |
| `approve_careplan` | `PUT /api/v1/careplans/{id}/status` | Approve or reject a care plan |

## Phase 1 CLI (temporary)

The Phase 1 CLI is a stopgap that will be replaced by the REST API implementation.

```bash
cd acp-writer
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

acp-writer patient-1   # Requires HAPI FHIR on :8080 and Kogito on :8081
```

### Phase 1 Shortcuts

These are intentional simplifications documented in the code. They must be replaced when the API is implemented.

- **Hardcoded FHIR-to-DMN mapping** — Specific to the hypertension decision tables. The API design eliminates this by having callers provide patient data directly and the service extracting what it needs.
- **Direct FHIR queries instead of IPS** — The API design eliminates this entirely. Callers provide patient data in the request body.

## Decision Service (Internal)

The Kogito decision service auto-generates REST endpoints from DMN files. This is an internal component — external callers should use the acp-writer API, not call Kogito directly.

```bash
# Direct Kogito access (internal/debugging only)
curl -X POST "http://localhost:8081/Treatment%20Recommendation" \
  -H "Content-Type: application/json" \
  -d '{"Systolic BP": 142, "Has Diabetes": true, "Has Kidney Disease": false}'
```
