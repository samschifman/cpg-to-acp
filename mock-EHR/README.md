# Mock Electronic Health Record

This contains the setup for the FHIR server that acts as an EHR proxy for the project. It also contains a client that acts as a very simple EHR and which the ACP Writer client can launch in.

## FHIR Server

Uses [HAPI FHIR](https://hapifhir.io/) JPA Server as a containerized FHIR R4 server. No custom Dockerfile is needed — the standard `hapiproject/hapi` image is used directly via podman-compose.

## Patient Data

Hand-crafted FHIR Transaction Bundles in `data/`:

| Bundle | Patient | Scenario | Expected DMN Path |
|---|---|---|---|
| `patient-bundle-medication.json` | James Reynolds, 55yo M | Hypertension (BP 142/92) + Type 2 Diabetes, on Metformin | `start_medication` — Lisinopril 10mg, 2-week follow-up, BMP in 4 weeks |
| `patient-bundle-lifestyle.json` | Maria Chen, 45yo F | Hypertension (BP 125/80), no comorbidities | `lifestyle_only` — 12-week follow-up, no medication, no labs |

## Data Loading

The `docker/load-data.sh` script waits for HAPI FHIR to be ready, then POSTs all JSON bundles from `data/` into the server. It runs as an init container via podman-compose.

## Verifying

After the data is loaded:

```bash
# List patients
curl http://localhost:8080/fhir/Patient

# Patient 1 conditions (should include hypertension + diabetes)
curl http://localhost:8080/fhir/Condition?patient=patient-1

# Patient 1 blood pressure (should be 142/92)
curl http://localhost:8080/fhir/Observation?patient=patient-1&category=vital-signs

# Patient 2 conditions (hypertension only)
curl http://localhost:8080/fhir/Condition?patient=patient-2

# Patient 2 blood pressure (should be 125/80)
curl http://localhost:8080/fhir/Observation?patient=patient-2&category=vital-signs
```
