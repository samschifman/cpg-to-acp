import { useCallback, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Flex,
  FlexItem,
  PageSection,
  Stack,
  StackItem,
  Title,
} from "@patternfly/react-core";
import { PipelineStepper, useAdaptivePolling } from "@cpg-to-acp/ui-shared";
import type { RunDetail } from "@app/api/models";
import { getRunDetail } from "@app/services/api";
import { toPipelineSteps } from "@app/pipeline/steps";

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [refreshKey, setRefreshKey] = useState(0);

  // fetcher carries runId + refreshKey so submitting a review restarts polling
  // (the run goes back to `running` after request_changes). See #125 fix: a new
  // fetcher identity is the intended restart trigger.
  const fetcher = useCallback(
    () => getRunDetail(runId!),
    [runId, refreshKey],
  );
  const isComplete = useCallback((r: RunDetail) => r.status !== "running", []);
  const { data: run } = useAdaptivePolling<RunDetail>({
    fetcher,
    isComplete,
    enabled: !!runId,
  });

  const steps = useMemo(() => toPipelineSteps(run?.steps ?? []), [run]);

  // Placeholder: the review gate + terminal navigation are wired in part B.
  const restartPolling = () => setRefreshKey((k) => k + 1);
  void navigate;
  void restartPolling;

  if (!run) {
    return (
      <PageSection>
        <Title headingLevel="h1">Loading run…</Title>
      </PageSection>
    );
  }

  return (
    <PageSection>
      <Flex direction={{ default: "column" }} gap={{ default: "gapLg" }}>
        <FlexItem>
          <Title headingLevel="h1">
            Care Plan Run{run.patient?.name ? ` — ${run.patient.name}` : ""}
          </Title>
          <p>Status: {run.status}</p>
        </FlexItem>
        <FlexItem>
          <Stack hasGutter>
            <StackItem>
              <Title headingLevel="h2">Pipeline</Title>
            </StackItem>
            <StackItem>
              <PipelineStepper steps={steps} />
            </StackItem>
          </Stack>
        </FlexItem>
      </Flex>
    </PageSection>
  );
}
