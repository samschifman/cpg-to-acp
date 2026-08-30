import {
  Card,
  CardBody,
  CardTitle,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
} from "@patternfly/react-core";
import type { PlanGoal } from "@app/api/models";

export function GoalCard({ goal }: { goal: PlanGoal }) {
  const hasProvenance =
    goal.rationale || goal.target || goal.sourceCpgId || goal.sourceRecommendationId;
  return (
    <Card isCompact>
      <CardTitle>{goal.description}</CardTitle>
      {hasProvenance && (
        <CardBody>
          <DescriptionList isHorizontal isCompact>
            {goal.target && (
              <DescriptionListGroup>
                <DescriptionListTerm>Target</DescriptionListTerm>
                <DescriptionListDescription>{goal.target}</DescriptionListDescription>
              </DescriptionListGroup>
            )}
            {goal.rationale && (
              <DescriptionListGroup>
                <DescriptionListTerm>Rationale</DescriptionListTerm>
                <DescriptionListDescription>{goal.rationale}</DescriptionListDescription>
              </DescriptionListGroup>
            )}
            {goal.sourceCpgId && (
              <DescriptionListGroup>
                <DescriptionListTerm>Source guideline</DescriptionListTerm>
                <DescriptionListDescription>{goal.sourceCpgId}</DescriptionListDescription>
              </DescriptionListGroup>
            )}
            {goal.sourceRecommendationId && (
              <DescriptionListGroup>
                <DescriptionListTerm>Source recommendation</DescriptionListTerm>
                <DescriptionListDescription>{goal.sourceRecommendationId}</DescriptionListDescription>
              </DescriptionListGroup>
            )}
          </DescriptionList>
        </CardBody>
      )}
    </Card>
  );
}
