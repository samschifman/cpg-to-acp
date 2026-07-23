# Spike E: mock-EHR Research

**Phase:** 4 | **Status:** Complete | **Date:** 2026-07-23

## Problem

We need a mock-EHR that:
1. Shows a patient list with clinical data
2. Launches the acp-writer as a SMART on FHIR app in patient context
3. Works with our existing HAPI FHIR server (patient data, care plans)
4. Runs on OpenShift

## Options Evaluated

### Option 1: Full Medplum (replace HAPI FHIR)

[Medplum](https://www.medplum.com/) is a full FHIR platform — server, React UI, SMART on FHIR, OAuth, Helm charts.

| Aspect | Assessment |
|---|---|
| FHIR server | FHIR R4, PostgreSQL-backed, US Core compliant |
| React UI | Tightly coupled to Medplum server SDK (`@medplum/react` depends on `@medplum/core` which targets Medplum's API) |
| SMART on FHIR | Built-in OAuth server, EHR launch + standalone launch |
| Self-hosting | Helm charts available, primarily AWS-oriented |
| License | Apache 2.0 |

**Verdict: STRONG CANDIDATE — reconsider.** Medplum provides a complete out-of-the-box EHR experience: patient search, charting (conditions, medications, vitals, care plans), care coordination, messaging, scheduling, and SMART on FHIR launch. Building all of this from scratch in PatternFly would be weeks of work that Medplum provides for free.

The migration from HAPI FHIR is manageable: Medplum is FHIR R4 compliant, so the same patient bundles and care plan resources work. The cpg-ingester delivery and acp-writer FHIR server writer just point to Medplum's FHIR endpoint instead of HAPI FHIR's. Patient data loads via Medplum's API the same way.

The React components ARE tightly coupled to Medplum's server, but that's fine if we use Medplum as the server. The coupling is a feature — the UI and server work together seamlessly.

### Option 2: HAPI FHIR + Medplum React Components

Use `@medplum/react` components against our existing HAPI FHIR backend.

**Verdict: NOT viable.** Research confirms `@medplum/react` depends on `@medplum/core` which is built for Medplum's API specifically (authentication, subscriptions, GraphQL). It's not a generic FHIR React library.

### Option 3: HAPI FHIR + SMART-EHR-Launcher (CSIRO) ← Recommended

[SMART-EHR-Launcher](https://github.com/aehrc/SMART-EHR-Launcher) is an open-source EHR simulator from CSIRO (Australia's national science agency). It's a React + TypeScript SPA built with Vite — exactly our tech stack.

| Aspect | Assessment |
|---|---|
| Technology | React, TypeScript, Vite — matches our Spike A stack perfectly |
| FHIR support | Works with any FHIR R4 server (uses the [smart-launcher-v2](https://github.com/smart-on-fhir/smart-launcher-v2) proxy to add SMART App Launch to vanilla FHIR servers) |
| SMART on FHIR | Full EHR launch flow with OAuth2 authorization_code + PKCE |
| Patient display | Shows conditions, medications, allergies, observations, encounters |
| Customization | Open source, React components, easy to modify look and feel |
| License | Apache 2.0 |
| Auth requirement | Uses the smart-launcher-v2 proxy as the OAuth server — no Keycloak needed |

**Key insight:** The smart-launcher-v2 proxy sits between the EHR-Launcher and our HAPI FHIR server. It handles the OAuth flow (authorization_code grant), injects patient context, and proxies FHIR requests. This means we get SMART on FHIR launch **without Keycloak and without replacing HAPI FHIR.**

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│  SMART-EHR  │────>│ smart-launcher-v2│────>│  HAPI FHIR  │
│  Launcher   │     │  (OAuth proxy)   │     │  (existing)  │
│  (React UI) │     │                  │     │             │
└─────────────┘     └──────────────────┘     └─────────────┘
       │
       │ EHR Launch
       ▼
┌─────────────┐
│ acp-writer  │
│    UI       │
│ (SMART app) │
└─────────────┘
```

### Option 4: HAPI FHIR + Custom PatternFly UI

Build the mock-EHR from scratch using PatternFly components.

**Verdict: Unnecessary effort.** SMART-EHR-Launcher already provides the patient list, clinical data display, and SMART launch flow. Building this from scratch in PatternFly would duplicate existing open-source work. We can customize SMART-EHR-Launcher's styling if needed (it's React/TypeScript).

## Decision

**Two viable approaches — evaluate both in Phase 4.0 implementation spike:**

### Approach A: Full Medplum (recommended for fastest demo)

Replace HAPI FHIR with Medplum. Get patient search, charting, care coordination, SMART on FHIR, and EHR UI out of the box. The mock-EHR IS Medplum.

| Pro | Con |
|---|---|
| Complete EHR UI for free (patient search, chart, care plans) | Replace a working HAPI FHIR with a new system |
| SMART on FHIR built in (no Keycloak, no smart-launcher-v2) | Medplum's UI doesn't use PatternFly (different look) |
| Self-hostable (Docker, Helm) | Need to validate FHIR R4 compatibility with our bundles |
| Less total work than building a custom EHR | Adds a dependency on Medplum's ecosystem |

### Approach B: HAPI FHIR + custom PatternFly EHR + smart-launcher-v2

Keep HAPI FHIR. Build the EHR shell in PatternFly. Use smart-launcher-v2 for SMART on FHIR OAuth.

| Pro | Con |
|---|---|
| Matches Red Hat AI design system | Significant frontend dev to build EHR features |
| HAPI FHIR unchanged, all tests pass | Need to build patient search, chart, clinical views |
| Full control over look and feel | smart-launcher-v2 is another service to deploy |

### Recommendation

**Start with Approach A (Medplum) for the fastest path to a demo.** If Medplum's look doesn't align with the demo's visual needs, or if FHIR compatibility issues arise, fall back to Approach B. The smart-launcher-v2 proxy is the common element — it works with both approaches.

SMART-EHR-Launcher is useful as a reference and for early testing, but the demo EHR needs to be built with PatternFly to match the Red Hat AI look and feel and to provide adequate clinical functionality.

### mock-EHR Features Needed

| Feature | Priority | Notes |
|---|---|---|
| Patient search | Must have | Search by name, MRN, condition |
| Patient list / worklist | Must have | Clinician's active patients |
| Patient demographics | Must have | Name, DOB, gender, identifiers |
| Conditions list | Must have | Active conditions with SNOMED/ICD codes |
| Medications list | Must have | Active medications with dosing |
| Observations / vitals | Must have | Recent BP, labs, HbA1c |
| Allergies | Should have | Active allergies |
| Care plan list | Must have | Show existing care plans from HAPI FHIR |
| SMART app launch | Must have | "Generate Care Plan" button launches acp-writer |
| Encounter context | Nice to have | Current encounter for the SMART launch |

### What Gets Built vs What Gets Reused

| Component | Build or Reuse |
|---|---|
| PatternFly EHR shell (layout, navigation) | Build |
| Patient search | Build (FHIR search API) |
| Patient chart view | Build (FHIR read API) |
| Clinical data display (conditions, meds, vitals) | Build with PatternFly Table/DataList |
| SMART on FHIR OAuth flow | Reuse smart-launcher-v2 proxy |
| Patient data | Reuse existing HAPI FHIR + synthetic patients |

## Deployment on OpenShift

| Component | Pod | Image |
|---|---|---|
| **mock-EHR UI** | `mock-ehr-ui` | Custom PatternFly React app (Nginx SPA) |
| **smart-launcher-v2** | `mock-ehr-auth` | Build from [smart-on-fhir/smart-launcher-v2](https://github.com/smart-on-fhir/smart-launcher-v2) (Node.js) |
| **HAPI FHIR** | `cpg-mock-ehr-hapi-fhir` | Already deployed, keep as-is |

## Look and Feel

PatternFly EHR shell with clinical dashboard layout:
- Left nav: patient worklist
- Main area: patient chart (tabbed: summary, conditions, medications, vitals, care plans)
- "Generate Care Plan" action button launches acp-writer SMART app in embedded view or new tab
- No Red Hat logo or name

## Phase 4 Integration Steps

1. Fork SMART-EHR-Launcher and smart-launcher-v2
2. Configure smart-launcher-v2 to proxy to our HAPI FHIR server
3. Deploy both as pods on OpenShift
4. Register acp-writer UI as a SMART app with the proxy
5. Test: click patient → launch acp-writer → generate care plan

## References

- [SMART-EHR-Launcher](https://github.com/aehrc/SMART-EHR-Launcher) — CSIRO EHR simulator (Apache 2.0)
- [smart-launcher-v2](https://github.com/smart-on-fhir/smart-launcher-v2) — SMART App Launch proxy
- [Medplum](https://www.medplum.com/) — evaluated but not selected
- [Medplum SMART on FHIR Demo](https://github.com/medplum/medplum-smart-on-fhir-demo)
- [SMART on FHIR Spec](https://docs.smarthealthit.org/)
- [Inferno SMART Test Kit](https://inferno.healthit.gov/test-kits/smart-app-launch/) — for conformance testing
