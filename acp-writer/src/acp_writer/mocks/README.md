# acp-writer mock BFF

A canned-data implementation of the PR #127 UI contract
(`acp-writer/api/bff-openapi.yaml`) for developing/demoing the React UI without
the real pipeline (no SonataFlow/MinIO/LLM/DMN/FHIR).

## Run locally

    cd acp-writer
    pip install -e '.[test]'
    uvicorn acp_writer.services.bff:app --port 8082 --reload

The UI's `vite.config.ts` already proxies `/api` and `/health` to `localhost:8082`,
so `npm run dev` in `acp-writer/ui` talks to this mock.

## Behavior

- A created run advances one automated step every ~2s, reaching
  `awaiting_careplan_review` (~14s) with a full `CarePlanView`.
- `POST /runs/{id}/review/careplan` with `approve` completes the run and persists
  the plan to `/careplans`; `request_changes` loops back to `running` and returns
  with `reviewIteration`/`previousFeedback` on the next gate.
- Two seed runs (one completed, one pinned at the gate) make the dashboard non-empty.

## Mode

Mock mode is active whenever `SONATAFLOW_URL` is unset. The SonataFlow-backed
branch is the real BFF's responsibility.

## Observability note

The mock deliberately omits MLflow tracing to preserve import hygiene (the slim
container installs only fastapi/uvicorn/pydantic). The chart still injects
`MLFLOW_TRACKING_URI` into the bff pod; the real SonataFlow-backed BFF should add
`mlflow.fastapi.autolog()` in its own branch (which does not require importing
mlflow into the `mocks/` package).
