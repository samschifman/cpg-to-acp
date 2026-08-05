import {
  Card,
  CardBody,
  CardTitle,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
} from "@patternfly/react-core";

interface GoalTarget {
  measure?: { text?: string };
  detailQuantity?: { value?: number; unit?: string };
}

export interface GoalResource {
  id?: string;
  description?: { text?: string };
  lifecycleStatus?: string;
  target?: GoalTarget[];
  startDate?: string;
}

export function GoalCard({ goal }: { goal: GoalResource }) {
  const target = goal.target?.[0];
  const targetDisplay = target?.detailQuantity
    ? `${target.detailQuantity.value} ${target.detailQuantity.unit ?? ""}`
    : "Not specified";

  return (
    <Card isCompact>
      <CardTitle>{goal.description?.text ?? "Goal"}</CardTitle>
      <CardBody>
        <DescriptionList isHorizontal isCompact>
          <DescriptionListGroup>
            <DescriptionListTerm>Target</DescriptionListTerm>
            <DescriptionListDescription>{targetDisplay}</DescriptionListDescription>
          </DescriptionListGroup>
          <DescriptionListGroup>
            <DescriptionListTerm>Measure</DescriptionListTerm>
            <DescriptionListDescription>
              {target?.measure?.text ?? "Not specified"}
            </DescriptionListDescription>
          </DescriptionListGroup>
          <DescriptionListGroup>
            <DescriptionListTerm>Status</DescriptionListTerm>
            <DescriptionListDescription>
              {goal.lifecycleStatus ?? "proposed"}
            </DescriptionListDescription>
          </DescriptionListGroup>
          {goal.startDate && (
            <DescriptionListGroup>
              <DescriptionListTerm>Start</DescriptionListTerm>
              <DescriptionListDescription>{goal.startDate}</DescriptionListDescription>
            </DescriptionListGroup>
          )}
        </DescriptionList>
      </CardBody>
    </Card>
  );
}
