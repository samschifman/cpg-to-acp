# Actionable Care Plan Writer

This is the heart of the project. It composes patient-specific, FHIR-compliant care plans by combining clinical decision logic with patient data.

## Architecture

The acp-writer contains two sub-components:

- **`decision-service/`** — Java/Quarkus application (Apache KIE 10.2 / Kogito) that exposes DMN decision tables as REST endpoints. This is the Drools decision engine runtime.
- **`src/acp_writer/`** — Python service that orchestrates the care plan composition pipeline: queries FHIR for patient data, invokes the decision service, and assembles a FHIR CarePlan Bundle.

Both the decision engine and the vector store (Phase 2) are internal implementation details of acp-writer.

## Two Outputs

1. **FHIR CarePlan** — Patient-specific care plan with goals, activities (MedicationRequests, ServiceRequests), and references back to the patient record.
2. **BPMN** (Phase 3) — Process definitions for automatable care plan activities, sent to the automation service.

## Phase 1 Usage

```bash
# Install
cd acp-writer
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Run (requires HAPI FHIR on :8080 and Kogito on :8081)
acp-writer patient-1                              # Output to stdout
acp-writer patient-1 -o careplan.json              # Output to file
acp-writer patient-1 --fhir-url http://fhir:8080/fhir --kogito-url http://kogito:8081
```

## Phase 1 Shortcuts

These are intentional simplifications documented in the code. They must be replaced in Phase 2.

- **Hardcoded FHIR-to-DMN mapping** — The code knows exactly which FHIR resources to query (Condition, Observation) and how to extract DMN inputs (systolic BP, diabetes boolean, kidney disease boolean). This is specific to the hypertension decision tables and does not generalize.
- **Direct FHIR queries instead of IPS** — Queries individual resource types rather than using the FHIR IPS `$summary` operation. Phase 2 should use IPS for a standardized patient summary.

## Decision Service

The Kogito decision service auto-generates REST endpoints from DMN files:

```bash
# Treatment Recommendation
curl -X POST "http://localhost:8081/Treatment%20Recommendation" \
  -H "Content-Type: application/json" \
  -d '{"Systolic BP": 142, "Has Diabetes": true, "Has Kidney Disease": false}'

# Monitoring Plan
curl -X POST "http://localhost:8081/Monitoring%20Plan" \
  -H "Content-Type: application/json" \
  -d '{"Treatment Action": "Start medication", "Has Kidney Disease": false}'
```

Input JSON keys must match DMN `inputData/@name` exactly.
