import { useCallback, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PageSection, Title } from "@patternfly/react-core";
import {
  PipelineStepper,
  useAdaptivePolling,
  type PipelineStep,
  type StepStatus,
} from "@cpg-to-acp/ui-shared";
import { AiReasoningPanel, type AiMessage } from "@app/components/AiReasoningPanel";
import type { CarePlanComposerState } from "@app/types/state";
import { getCarePlan } from "@app/services/api";

interface PipelineStepDef {
  id: string;
  label: string;
  stateKey: keyof CarePlanComposerState;
}

const PIPELINE_STEPS: PipelineStepDef[] = [
  { id: "condition_scanner", label: "Patient data scanned", stateKey: "condition_codes" },
  { id: "guideline_resolver", label: "Guidelines resolved", stateKey: "applicable_cpgs" },
  { id: "dmn_executor", label: "DMN decisions evaluated", stateKey: "dmn_results" },
  { id: "recommendation_retriever", label: "Recommendations retrieved", stateKey: "recommendations" },
  { id: "plan_composer", label: "Care plan composed", stateKey: "planning_brief" },
  { id: "brief_reviewer", label: "Brief reviewed", stateKey: "brief_review_count" },
  { id: "fhir_bundle_generator", label: "FHIR bundle generated", stateKey: "fhir_bundle" },
  { id: "validators", label: "Terminology + syntax validated", stateKey: "syntax_errors" },
  { id: "fhir_semantic_reviewer", label: "Clinical review", stateKey: "fhir_review_count" },
  { id: "fhir_server_writer", label: "Written to FHIR server", stateKey: "delivery_status" },
];

function deriveSteps(state: CarePlanComposerState | null): PipelineStep[] {
  if (!state) {
    return PIPELINE_STEPS.map((s) => ({ id: s.id, label: s.label, status: "pending" as StepStatus }));
  }

  let foundRunning = false;
  return PIPELINE_STEPS.map((step) => {
    if (foundRunning) {
      return { id: step.id, label: step.label, status: "pending" as StepStatus };
    }
    const value = state[step.stateKey];
    const hasValue = value !== undefined && value !== null;
    if (!hasValue) {
      foundRunning = true;
      return { id: step.id, label: step.label, status: "running" as StepStatus };
    }
    return { id: step.id, label: step.label, status: "complete" as StepStatus };
  });
}

function deriveMessages(state: CarePlanComposerState | null): AiMessage[] {
  if (!state) return [];
  const messages: AiMessage[] = [];

  if (state.applicable_cpgs) {
    const cpgs = state.applicable_cpgs;
    messages.push({
      role: "ai",
      content: `Resolved ${cpgs.length} applicable guideline(s).`,
    });
  }
  if (state.dmn_results) {
    messages.push({
      role: "ai",
      content: `Evaluated ${state.dmn_results.length} DMN decision model(s).`,
    });
  }
  if (state.recommendations) {
    messages.push({
      role: "ai",
      content: `Retrieved ${state.recommendations.length} recommendation(s).`,
    });
  }
  if (state.brief_review_feedback) {
    messages.push({
      role: "ai",
      content: `Brief review (iteration ${state.brief_review_count}): revision needed.`,
    });
  }
  if (state.planning_brief && !state.brief_review_feedback) {
    messages.push({ role: "ai", content: "Planning brief approved." });
  }
  if (state.terminology_issues && state.terminology_issues.length > 0) {
    messages.push({
      role: "system",
      content: `Terminology validation: ${state.terminology_issues.length} issue(s) found.`,
    });
  }
  if (state.fhir_review_feedback) {
    messages.push({
      role: "ai",
      content: `FHIR review (iteration ${state.fhir_review_count}): revision needed.`,
    });
  }
  if (state.delivery_status) {
    messages.push({ role: "system", content: `Delivery: ${state.delivery_status}` });
  }

  return messages;
}

export function GenerationProgress() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const fetcher = useCallback(
    () => getCarePlan(runId!) as Promise<CarePlanComposerState>,
    [runId],
  );

  const isComplete = useCallback(
    (state: CarePlanComposerState) => !!state.delivery_status,
    [],
  );

  const { data: state } = useAdaptivePolling({
    fetcher,
    isComplete,
    enabled: !!runId,
  });

  const steps = useMemo(() => deriveSteps(state), [state]);
  const messages = useMemo(() => deriveMessages(state), [state]);

  if (state?.delivery_status && state.careplan_id) {
    navigate(`/plans/${state.careplan_id}`, { replace: true });
  }

  return (
    <PageSection>
      <Title headingLevel="h1">
        Generating Care Plan
        {state?.patient_reference ? ` for ${state.patient_reference}` : ""}
      </Title>

      <PipelineStepper steps={steps} />

      {messages.length > 0 && (
        <>
          <Title headingLevel="h2">AI Reasoning</Title>
          <AiReasoningPanel messages={messages} />
        </>
      )}
    </PageSection>
  );
}
