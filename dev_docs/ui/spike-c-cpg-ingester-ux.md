# Spike C: cpg-ingester UX Design

**Phase:** 4 | **Status:** Complete | **Date:** 2026-07-23

## User Profile

The cpg-ingester UI is used by **clinical informaticists** — people who understand both clinical guidelines and health IT. They upload CPGs, review what the AI extracted, correct errors, and approve artifacts for delivery to acp-writer. This is an admin/authoring tool, not a clinician-facing application.

No authentication needed for the Phase 4 demo. No patient data involved — all content is clinical guideline material (non-PHI).

## Overall Flow

```mermaid
graph LR
    A[Upload PDF] --> B[Parsing]
    B --> C[Review Structure]
    C --> D[Review Items]
    D --> E[Review DMN]
    E --> F[Review Recommendations]
    F --> G[Approve & Deliver]
```

The flow mirrors the pipeline steps. Each screen shows the AI's output for that step and lets the user review before proceeding. The pipeline runs via SonataFlow async callbacks — the UI polls for progress (see Spike B).

## Screens

### 1. Dashboard / Run List

The landing page. Shows all pipeline runs with status.

| Element | Content |
|---|---|
| **Page title** | CPG Ingester |
| **Action** | "Upload CPG" button (primary) |
| **Run list** | Table: CPG name, upload date, status (parsing/analyzing/complete/failed), actions |
| **Status indicators** | PatternFly Label components: `Parsing`, `Analyzing`, `Assembling`, `Delivering`, `Complete`, `Failed` |

Clicking a run opens the detail view.

### 2. Upload

Simple upload flow — drag-and-drop or file picker.

| Element | Content |
|---|---|
| **Drop zone** | PatternFly FileUpload or custom drop zone for PDF |
| **Validation** | File type check (PDF only), size warning if >50MB |
| **Action** | Upload to MinIO → trigger SonataFlow workflow |
| **After upload** | Redirect to run detail with live status polling |

### 3. Run Detail — Live Progress

Shows pipeline progress as a vertical step tracker. Each step shows status and timing. Uses PatternFly ProgressStepper or Wizard component.

```
┌─────────────────────────────────────┐
│  Synthetic Hypertension CPG v1.0    │
│  Uploaded: 2026-07-23 14:30         │
├─────────────────────────────────────┤
│  ✅ Parse (Docling)        1m 23s   │
│  ⏳ Analyze (LLM)          running  │
│  ○  Assemble                        │
│  ○  Deliver to acp-writer           │
├─────────────────────────────────────┤
│  [View Details]                     │
└─────────────────────────────────────┘
```

When a step completes, its output becomes reviewable. Uses the PatternFly ChatBot message pattern to show AI reasoning as a conversation:

```
┌─────────────────────────────────────┐
│ 🤖 Structure Analyzer              │
│ Identified 12 sections:            │
│ • 3.1 First-Line Medication (rec)  │
│ • 3.2 Blood Pressure Targets (dec) │
│ • 3.3 Lifestyle Modifications (rec)│
│ ...                                │
│                                    │
│ 🤖 Classification Reviewer         │
│ REVISION NEEDED: Section 3.4       │
│ should be classified as "decision" │
│ not "recommendation" because it    │
│ contains threshold-based logic.    │
│                                    │
│ 🤖 Item Identifier (revised)       │
│ Updated classification for 3.4.   │
│ Final manifest: 4 decisions,       │
│ 8 recommendations.                 │
└─────────────────────────────────────┘
```

### 4. Structure Review

Shows the CPG's section structure with AI classifications. Users can see how the AI interpreted the document.

| Element | Content |
|---|---|
| **Section tree** | PatternFly TreeView — hierarchical sections with classification labels |
| **Classification labels** | `decision`, `recommendation`, `background`, `methods` — color-coded |
| **Source text** | Expandable panel showing the original CPG text for each section |
| **CPG metadata** | Side panel: title, version, issuing body, scope, grading system |

### 5. Decision Review (DMN)

Shows extracted DMN decision tables with traceability back to CPG source.

| Element | Content |
|---|---|
| **Decision list** | PatternFly DataList — one card per DMN model |
| **Each card shows** | Decision name, input variables, output variables, source section reference |
| **DMN visualization** | Read-only decision table rendered as a PatternFly Table (inputs as columns, rules as rows, outputs as results) |
| **Source reference** | "From section 3.2" link — highlights the source text in the CPG |
| **DMN XML** | Expandable code block (PatternFly CodeBlock) with syntax highlighting |
| **Validation status** | Syntax valid ✅, Semantic review: approved ✅ |

> **Deferred:** Interactive DMN editing (Phase 8). For now, users can only view, not modify.

### 6. Recommendation Review

Shows extracted recommendations with metadata and traceability.

| Element | Content |
|---|---|
| **Recommendation list** | PatternFly DataList — one card per recommendation |
| **Each card shows** | Title, type (treatment/lifestyle/monitoring), strength, evidence quality |
| **Content** | Full recommendation text (expandable) |
| **Source reference** | Section and page number from the CPG |
| **Cross-references** | Links to related DMN decisions or other recommendations |
| **Certainty badge** | PatternFly Label: `Strong For`, `Conditional For`, etc. |

> **Deferred:** Recommendation editing (Phase 8). For now, view-only.

### 7. Assembly Report

Shows cross-reference resolution and integrity check results.

| Element | Content |
|---|---|
| **Summary** | Total items, cross-references resolved, escalated items |
| **Escalated items** | PatternFly Alert list — items that failed validation |
| **Assembly report** | Expandable detail panel |

### 8. Approval & Delivery

Final review before delivering artifacts to acp-writer.

| Element | Content |
|---|---|
| **Summary** | CPG metadata, counts (decisions, recommendations), target acp-writer URL |
| **Artifact list** | What will be delivered: guidelines metadata, DMN models, recommendation bundle |
| **Actions** | "Deliver to acp-writer" (primary), "Cancel" (secondary) |
| **Delivery status** | Success/failure for each artifact type |

## CPG → Artifact Lineage (Traceability)

A key UX requirement: the user needs to see WHERE in the CPG each decision/recommendation came from. This is implemented as bidirectional navigation:

- **Forward:** Section → items extracted from it (decisions, recommendations)
- **Backward:** Decision/recommendation → source section + original text

PatternFly TreeView with section nodes that expand to show extracted items. Clicking an item scrolls to its detail card. Clicking "Source" on a detail card scrolls to the section tree.

```
CPG: Hypertension Management v1.0
├── 3. Treatment Recommendations
│   ├── 3.1 First-Line Medication
│   │   ├── [REC] Lisinopril 10mg initial dose (strong-for)
│   │   └── [REC] Monitor renal function at 2 weeks
│   ├── 3.2 Blood Pressure Targets
│   │   └── [DMN] BP Target Decision Table
│   ├── 3.3 Lifestyle Modifications
│   │   ├── [REC] DASH diet counseling
│   │   └── [REC] 150min/week exercise
```

## Async Interaction Pattern

Per Spike B, the UI polls the SonataFlow workflow:

1. Upload PDF → store in MinIO → trigger `cpgingester` workflow → get workflow ID
2. Poll `GET /cpgingester/{id}` every 5 seconds
3. As each step's data appears in the workflow state (parseResult, analysisResult, etc.), unlock that review screen
4. User reviews each step's output at their own pace
5. Delivery is triggered by the workflow automatically (sync step), or could be gated on user approval

### Future: Human-in-the-Loop (Phase 8)

In a future phase, the user could pause the pipeline between steps to make corrections. This would use SonataFlow Callback states where the "callback" comes from the UI (user clicks "Approve and Continue"). For Phase 4, the pipeline runs to completion automatically and the user reviews afterward.

## PatternFly Components Used

| Component | Where |
|---|---|
| Page, PageSection | Overall layout |
| Card, CardBody | Run summary, artifact cards |
| DataList | Decision list, recommendation list |
| TreeView | Section structure with classifications |
| Table | DMN decision table visualization |
| FileUpload | PDF upload |
| ProgressStepper | Pipeline step progress |
| Label | Classification tags, certainty badges |
| Alert | Escalated items, validation errors |
| CodeBlock | DMN XML display, FHIR JSON |
| ExpandableSection | Collapsible detail panels |
| ChatBot (Message) | AI reasoning display per step |
| Tabs | Detail view sections (structure, decisions, recommendations) |

## References

- Spike A: Technology stack (PatternFly 6, React, TypeScript)
- Spike B: Backend interaction (polling, async pattern)
- `cpg-ingester/src/cpg_ingester/services/` — service APIs
- `cpg-ingester/deploy/orchestrator/cpg-ingester-workflow.yaml` — SonataFlow workflow
