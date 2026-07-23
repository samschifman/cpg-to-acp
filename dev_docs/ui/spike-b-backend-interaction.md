# Spike B: UI ↔ Backend Interaction Pattern

**Phase:** 4 | **Status:** Complete | **Date:** 2026-07-23

## Problem

The backend uses SonataFlow with async callbacks for LLM-heavy steps. A pipeline run takes 3-10 minutes (Docling parsing + multiple LLM calls + FHIR generation). The UI **must not** make blocking calls — it needs to trigger work, show progress, and display results as they arrive.

Additionally, the system includes human-in-the-loop review steps (clinician approves/rejects care plans, reviews recommendations). These need to pause the pipeline and wait for human input.

## Decision

**Polling with SonataFlow workflow REST API + direct service calls for human actions.**

The UI does NOT talk to SonataFlow via CloudEvents or callbacks. Instead:

1. **Trigger:** UI POSTs to the SonataFlow workflow endpoint to start a pipeline run
2. **Poll:** UI polls the workflow instance for status and intermediate results
3. **Display:** As each async step completes (its data appears in the workflow state), the UI updates
4. **Human action:** For approve/reject, the UI calls the service endpoints directly (e.g., PUT to fhir-server for care plan status)

```
┌──────────┐          ┌───────────┐          ┌──────────────┐
│   UI     │          │ SonataFlow │          │  Pod Services│
│ (React)  │          │ Workflow   │          │  (FastAPI)   │
└────┬─────┘          └─────┬─────┘          └──────┬───────┘
     │                      │                       │
     │ POST /cpgingester    │                       │
     │ {pdf_ref: "..."}     │                       │
     │─────────────────────>│                       │
     │      201 {id: "..."}│                        │
     │<─────────────────────│                       │
     │                      │ POST /parse-async     │
     │                      │──────────────────────>│
     │                      │      200 accepted     │
     │                      │<──────────────────────│
     │                      │                       │
     │ GET /cpgingester/{id}│                       │ (parsing...)
     │─────────────────────>│                       │
     │  {status: "accepted"}│                       │
     │<─────────────────────│                       │
     │                      │                       │
     │         ...polling...│                       │
     │                      │   CloudEvent callback │
     │                      │<──────────────────────│
     │                      │                       │
     │ GET /cpgingester/{id}│                       │
     │─────────────────────>│                       │
     │  {parseResult: {...}}│                       │
     │<─────────────────────│                       │
     │                      │                       │
     │  (UI shows parse     │                       │
     │   results to user)   │                       │
```

## Why Polling (Not WebSockets or SSE)

| Option | Pros | Cons |
|---|---|---|
| **Polling** | Simplest. Works through all proxies/load balancers. Stateless — refreshing the page resumes from last state. SonataFlow already has a REST API for querying workflow instances. | Latency between updates (poll interval). Wasted requests when nothing changed. |
| **WebSockets** | Real-time updates. No wasted requests. | Requires WebSocket support in all proxy layers (API gateway, OpenShift Route). Stateful connections — page refresh loses context. Need a new WebSocket service. |
| **SSE (Server-Sent Events)** | Real-time, simpler than WebSockets. Works through most proxies. | Need a new SSE endpoint. SonataFlow doesn't have one natively. |

**Polling wins** because:
1. SonataFlow already exposes `GET /cpgingester/{id}` and `GET /acpwriter/{id}` — zero backend work needed
2. The pipeline runs for minutes — polling every 5-10 seconds is fine (not real-time chat)
3. Stateless — user can close the browser and come back, the workflow is still running
4. No proxy/networking concerns (WebSockets through OpenShift Routes need special configuration)

### Optimization: Adaptive Polling

Start polling at 2-second intervals. After 30 seconds with no state change, slow to 10 seconds. After 2 minutes, slow to 30 seconds. Reset to fast polling when state changes.

## Human-in-the-Loop Pattern

For steps that need clinician input (approve/reject care plan, review recommendations), the UI calls service endpoints directly — NOT through SonataFlow.

**Why:** SonataFlow orchestrates the automated pipeline. Human review is outside the workflow — the care plan is already written to the FHIR server, and approval changes its status. The UI calls `PUT /api/v1/careplans/{id}/status` directly through the API gateway.

If future phases need human-in-the-loop WITHIN the pipeline (e.g., clinician reviews recommendations before compose), that would use a SonataFlow Callback state where the callback comes from the UI (the clinician's action sends the CloudEvent). This is the same pattern as the LLM async callbacks but with a human providing the response instead of a service.

```
SonataFlow                    UI (React)
    │                           │
    │ POST /review-step-async   │
    │ {callback_url, data...}   │
    │──────────(to service)────>│
    │                           │
    │ (workflow WAITING)        │ (UI shows review screen)
    │                           │
    │                           │ User clicks "Approve"
    │                           │
    │ POST /wait-review         │
    │ CloudEvent {approved}     │
    │<──────────────────────────│
    │                           │
    │ (workflow RESUMES)        │
```

This pattern is designed but **deferred** — Phase 4 UIs use the simpler post-pipeline approve/reject pattern.

## API Endpoints the UI Calls

### cpg-ingester UI

| Action | Method | Endpoint | Through |
|---|---|---|---|
| Upload PDF to MinIO | PUT | MinIO S3 API | Direct (presigned URL) or via upload service |
| Start ingestion | POST | `/cpgingester` | SonataFlow workflow |
| Poll status | GET | `/cpgingester/{id}` | SonataFlow workflow |
| List runs | GET | `/cpgingester` | SonataFlow workflow |
| View artifacts | GET | MinIO S3 API | Direct |

### acp-writer UI

| Action | Method | Endpoint | Through |
|---|---|---|---|
| Start care plan generation | POST | `/acpwriter` | SonataFlow workflow |
| Poll status | GET | `/acpwriter/{id}` | SonataFlow workflow |
| List care plans | GET | `/api/v1/careplans` | API gateway |
| View care plan | GET | `/api/v1/careplans/{id}` | API gateway |
| Approve care plan | PUT | `/api/v1/careplans/{id}/status` | API gateway |
| Reject care plan | PUT | `/api/v1/careplans/{id}/status` | API gateway |
| List patients | MCP | `ehr_list_patients` | MCP Gateway |
| Get patient summary | MCP | `ehr_get_patient_summary` | MCP Gateway |

### Authentication (Phase 4 lightweight)

For the Phase 4 demo, the UI talks to the SonataFlow and API gateway endpoints without authentication. Patient context is passed directly (not via SMART on FHIR token). The lightweight auth (Medplum built-in, Keycloak minimal, or mock stub) is added in Phase 4 step 4.4.

## State Management

Use React Query (TanStack Query) for:
- Polling with `refetchInterval`
- Cache management
- Optimistic updates for approve/reject

```typescript
const { data: workflow } = useQuery({
  queryKey: ['workflow', workflowId],
  queryFn: () => fetchWorkflowStatus(workflowId),
  refetchInterval: (data) => {
    if (data?.workflowdata?.status === 'completed') return false
    return 5000 // 5 second poll
  },
})
```

## Error Handling

- If SonataFlow workflow errors (LLM failure, MinIO unreachable), the workflow state includes the error message. The UI displays it with a retry option.
- If a service is down, the SonataFlow workflow stays in waiting state. The UI shows "waiting for [step name]..." and the clinician can check back later.
- Network errors from the UI to the backend → standard React Query retry with exponential backoff.

## References

- [SonataFlow REST API](https://sonataflow.org/serverlessworkflow/latest/) — workflow instance query
- [TanStack Query](https://tanstack.com/query/latest) — React data fetching with polling
- [PatternFly ChatBot](https://www.patternfly.org/patternfly-ai/chatbot/about-chatbot/) — for displaying pipeline progress as a conversation
- `dev_docs/spike-async-callback.md` — the backend async pattern this UI consumes
