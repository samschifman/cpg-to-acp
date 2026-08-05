import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Label,
  PageSection,
  Title,
} from "@patternfly/react-core";
import { Table, Tbody, Td, Th, Thead, Tr } from "@patternfly/react-table";
import { useAdaptivePolling, type CarePlanSummary } from "@cpg-to-acp/ui-shared";
import { listCarePlans } from "@app/services/api";

const statusColor: Record<string, "blue" | "green" | "red"> = {
  draft: "blue",
  active: "green",
  "entered-in-error": "red",
};

export function CarePlanList() {
  const navigate = useNavigate();
  const fetcher = useCallback(() => listCarePlans(), []);
  const { data: plans } = useAdaptivePolling<CarePlanSummary[]>({
    fetcher,
    isComplete: () => true,
  });

  return (
    <PageSection>
      <Title headingLevel="h1">Care Plans</Title>
      <Table aria-label="Care plans">
        <Thead>
          <Tr>
            <Th>Patient</Th>
            <Th>Status</Th>
            <Th>Generated</Th>
            <Th>Actions</Th>
          </Tr>
        </Thead>
        <Tbody>
          {(plans ?? []).map((plan) => (
            <Tr key={plan.id}>
              <Td>{plan.patient_reference}</Td>
              <Td>
                <Label color={statusColor[plan.status] ?? "blue"}>
                  {plan.status}
                </Label>
              </Td>
              <Td>{new Date(plan.generated_at).toLocaleString()}</Td>
              <Td>
                <Button
                  variant="link"
                  onClick={() => navigate(`/plans/${plan.id}`)}
                >
                  View
                </Button>
              </Td>
            </Tr>
          ))}
          {plans && plans.length === 0 && (
            <Tr>
              <Td colSpan={4}>No care plans generated yet.</Td>
            </Tr>
          )}
        </Tbody>
      </Table>
    </PageSection>
  );
}
