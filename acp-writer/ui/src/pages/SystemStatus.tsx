import { useCallback } from "react";
import {
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Label,
  PageSection,
  Title,
} from "@patternfly/react-core";
import { useAdaptivePolling, type ServiceStatus as ServiceStatusType } from "@cpg-to-acp/ui-shared";
import { getSystemStatus } from "@app/services/api";

export function SystemStatus() {
  const fetcher = useCallback(() => getSystemStatus(), []);
  const { data: status, error } = useAdaptivePolling<ServiceStatusType>({
    fetcher,
    isComplete: () => true,
  });

  return (
    <PageSection>
      <Title headingLevel="h1">System Status</Title>
      {error && <p>Failed to load status: {error.message}</p>}
      {status && (
        <DescriptionList isHorizontal>
          <DescriptionListGroup>
            <DescriptionListTerm>Version</DescriptionListTerm>
            <DescriptionListDescription>{status.version}</DescriptionListDescription>
          </DescriptionListGroup>
          <DescriptionListGroup>
            <DescriptionListTerm>Decision Engine</DescriptionListTerm>
            <DescriptionListDescription>
              <Label color={status.decision_engine.available ? "green" : "red"}>
                {status.decision_engine.available ? "Available" : "Unavailable"}
              </Label>{" "}
              ({status.decision_engine.models} models)
            </DescriptionListDescription>
          </DescriptionListGroup>
          <DescriptionListGroup>
            <DescriptionListTerm>Knowledge Base</DescriptionListTerm>
            <DescriptionListDescription>
              {status.knowledge_base.guidelines} guidelines,{" "}
              {status.knowledge_base.recommendations} recommendations
            </DescriptionListDescription>
          </DescriptionListGroup>
        </DescriptionList>
      )}
    </PageSection>
  );
}
