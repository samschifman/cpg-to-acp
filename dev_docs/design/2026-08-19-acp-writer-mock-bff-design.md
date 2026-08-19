# acp-writer mock BFF — design

**Date:** 2026-08-19
**Branch:** `acp-writer-bff-mock` (worktree `.claude/worktrees/acp-writer-bff`, based on `bff-ui-contract`)
**Author:** Khaled (pet implementation) — the "real" SonataFlow-backed BFF is Jaideep's.

## Goal

Give the acp-writer React UI a backend it can be developed and demoed against
**today**, without the heavy pipeline. It must satisfy PR #127's contract
(`acp-writer/api/bff-openapi.yaml`) with canned data so every UI screen — including
the care-plan review loop — can be exercised deterministically.

## Why a mock is the right (and only) tool here

- The contract's central state, `awaiting_careplan_review`, **cannot be produced by
  the real backend yet.** The SonataFlow workflow
  (`acp-writer/deploy/orchestrator/acp-writer-workflow.yaml`) runs
  `…ReviewFHIR (automated) → CheckFHIRVerdict → WriteFHIR → Done` with no human gate.
  The human care-plan gate is unbuilt (follow-up #129). The mock is the only way to
  drive the review UI.
- It decouples UI iteration from backend readiness/cost (no SonataFlow, MinIO, DMN,
  LLM, or FHIR server; no cluster-admin provisioning).
- It is a **contract-conformance harness**: responses are shaped to the same OpenAPI
  that generates the UI's `types.ts`.

## Architecture

One FastAPI app, mirroring the cpg-ingester BFF pattern
(`cpg-ingester/src/cpg_ingester/services/bff.py`), where SonataFlow/MinIO are
independently optional and a `mocks/` package serves canned data when unconfigured.

- `acp_writer.services.bff:app` — FastAPI app. When `SONATAFLOW_URL` is unset it
  mounts the mock router (this is the mode we run). The SonataFlow-backed branch is a
  clearly-marked stub for Jaideep to fill.
- **The local and in-cluster BFF are the same app** — only packaging differs. Mock
  mode has **zero backend dependencies**; it serves an in-memory store.

```
Local:    vite dev  --/api-->  uvicorn acp_writer.services.bff:app  (:8082, mock)
Cluster:  ui pod (nginx) --/api--> acp-writer-bff Service --> bff pod (mock)
```

On-cluster this needs **exactly two pods** — `bff` (mock) + `ui` (React SPA). It skips
the five OpenShell sandboxes, SonataFlow, MinIO, MaaS, and the openshell/namespace
provisioning.

## Components (new files)

| File | Purpose |
|---|---|
| `acp-writer/src/acp_writer/services/bff.py` | FastAPI app; mock-mode wiring + health; stubbed SonataFlow branch |
| `acp-writer/src/acp_writer/mocks/__init__.py` | package marker |
| `acp-writer/src/acp_writer/mocks/data.py` | canned view-models: patients, runs, a `CarePlanView`, persisted careplans |
| `acp-writer/src/acp_writer/mocks/router.py` | the 8 UI endpoints + in-memory run-state progression |
| `acp-writer/deploy/pods/Containerfile.bff` | UBI image, `uvicorn …bff:app` (mirror ingester) |
| `acp-writer/tests/test_bff_contract.py` | validates mock responses against `bff-openapi.yaml` |

**Import hygiene:** `bff.py` and `mocks/` must NOT import the heavy pipeline
(langgraph/mlflow/DMN/LLM). Keep imports minimal so the image and local run stay light.

## Endpoints (PR #127, UI-facing)

Base path `/api/v1`. All responses match the contract schemas exactly.

- `POST /runs` — accept `{ipsBundle}`, create a run, return `RunCreated` (202).
- `GET /runs` — `RunSummary[]`, newest first; optional `status`/`limit`.
- `GET /runs/{id}` — `RunDetail` (the crux object; polled).
- `DELETE /runs/{id}` — cancel (204).
- `POST /runs/{id}/review/careplan` — `ReviewAction` → `approve` | `request_changes`; returns updated `RunDetail` (202); 409 if not at the gate.
- `GET /careplans` — `CarePlanSummary[]`.
- `GET /careplans/{id}` — `CarePlanDetail` (read-only).
- `GET /status` — `SystemStatus` (canned: engine up, KB counts).
- `GET /health` — liveness (mirrors ingester; reports mock mode).

## Run state progression (the useful part)

A created run advances through `StepKey`s over wall-clock time so the UI's polling,
stepper, and gate all animate realistically:

```
running (steps advance: scan_patient → … → generate_bundle/review_fhir)
   ↓  (after N seconds)
awaiting_careplan_review   — RunDetail.carePlan = a full CarePlanView, awaitingReview=careplan
   ↓ POST review/careplan
   ├─ approve          → completed; careplan persisted (appears in GET /careplans)
   └─ request_changes  → running again; on next gate reviewIteration++ and
                          previousFeedback = the submitted ReviewAction
```

Progression is time-derived from `createdAt` (deterministic given elapsed time), so no
background threads are required. `feedback[].itemId` references the stable
goal/activity/conflict IDs in the served `CarePlanView`.

## Canned data

- 2–3 seed runs at different statuses (one already at the gate, one completed, one
  running) so `GET /runs` and the dashboard look real on first load.
- One rich `CarePlanView`: a few `PlanGoal`/`PlanActivity`/`PlanConflict` with stable
  IDs, plus a small but valid `fhirBundle` for the "View FHIR JSON" viewer.
- 1–2 persisted `CarePlanSummary`/`CarePlanDetail`.
- A `PatientSummary` (name, demographics, a few conditions/meds) per run.

## Framework integration (in-cluster)

- **Add a `bff` pod** to `acp-writer/deploy/chart-pods/values.yaml` (`sandboxed: false`,
  port 8080, no secrets, no `sonataflowUrl` → mock mode), mirroring the ingester chart.
- **Extend `chart-pods/templates/deployments.yaml`** to handle `bff`-style env
  (`bffHost`, `sonataflowUrl`, `minioEndpoint`) — acp-writer's chart is a slim copy
  that lacks it; the ingester chart already has it (port that block over).
- **Point the `ui` pod at the BFF** via `env.bffHost: acp-writer-bff:8080` (nginx
  `${API_URL}` proxy). The `ui` pod serving React instead of Jinja is the *other*
  session's work; we only provide the target.
- A minimal "just these two pods" install path (enable only `bff` + `ui`) for
  lightweight cluster testing.

## Local dev

`uvicorn acp_writer.services.bff:app --port 8082` (mock mode by default) + `vite dev`
in `acp-writer/ui` — the existing vite proxy already targets `localhost:8082`.

## Security

Do **not** copy the reference BFF's `CORSMiddleware(allow_origins=["*"])`. The SPA is
served same-origin through nginx, so scope CORS to the dev origin (`localhost:3001`)
and drop it in-cluster. No PHI is persisted (in-memory canned data only).

## Non-goals

- No real SonataFlow/MinIO/DMN/LLM/FHIR integration (Jaideep's real BFF).
- No changes to the React UI (other session) beyond providing the `bffHost` target.
- Not building the #129 workflow gate; the mock stands in for it.

## Flags surfaced (to revisit, tracked separately)

1. **#129 — no care-plan human gate in the workflow.** Real end-to-end review is
   blocked until this lands; the mock is the interim.
2. **Contract hygiene** — `StepKey.review_careplan` comment still describes the removed
   post-write `PUT /careplans/{id}/status` path; contradicts the in-run-gate decision.
3. **`chart-pods` gap** — acp-writer's chart lacks the bff/env handling the ingester
   chart has.
4. **CORS `*`** in the reference BFF — tighten when mirroring.

## Ownership boundary

Khaled owns the mock path (mocks package + mock-mode wiring + Containerfile + chart
pod). Jaideep owns the real SonataFlow-backed branch of `bff.py`; this design leaves it
a clean, marked stub so his work drops in without conflict.

## Testing

- `test_bff_contract.py`: for each endpoint, assert the response validates against the
  corresponding schema in `bff-openapi.yaml` (openapi-core or jsonschema).
- Manual: `vite dev` walkthrough of every screen incl. the request_changes loop.
- Cluster milestone: deploy `bff` + `ui`, confirm the nginx `/api` seam works end-to-end.
