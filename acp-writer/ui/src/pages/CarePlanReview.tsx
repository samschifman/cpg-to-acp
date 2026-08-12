import { useCallback, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Button,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Flex,
  FlexItem,
  Label,
  PageSection,
  Stack,
  StackItem,
  Tab,
  Tabs,
  TabTitleText,
  Title,
} from "@patternfly/react-core";
import { useAdaptivePolling } from "@cpg-to-acp/ui-shared";
import { FhirJsonViewer } from "@app/components/FhirJsonViewer";
import { getCarePlan } from "@app/services/api";
import { GoalCard, type GoalResource } from "@app/components/GoalCard";
import { ActivityCard, type ActivityResource } from "@app/components/ActivityCard";
import { ConflictAlert, type Conflict } from "@app/components/ConflictAlert";
import { ApprovalDialog } from "@app/components/ApprovalDialog";
import { RejectionDialog } from "@app/components/RejectionDialog";

interface FhirBundle {
  resourceType: string;
  entry?: Array<{ resource: { resourceType: string; [key: string]: unknown } }>;
  [key: string]: unknown;
}

function getResources(bundle: FhirBundle, type: string) {
  return (bundle.entry ?? [])
    .map((e) => e.resource)
    .filter((r) => r.resourceType === type);
}

const statusColor: Record<string, "blue" | "green" | "red"> = {
  draft: "blue",
  active: "green",
  "entered-in-error": "red",
};

export function CarePlanReview() {
  const { id } = useParams<{ id: string }>();
  const [activeTab, setActiveTab] = useState(0);
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const fetcher = useCallback(() => getCarePlan(id!), [id, refreshKey]);
  const { data: bundle } = useAdaptivePolling({
    fetcher,
    isComplete: () => true,
    enabled: !!id,
  });

  if (!bundle) {
    return (
      <PageSection>
        <Title headingLevel="h1">Loading care plan...</Title>
      </PageSection>
    );
  }

  const fhirBundle = bundle as unknown as FhirBundle;
  const carePlan = getResources(fhirBundle, "CarePlan")[0] ?? {};
  const goals = getResources(fhirBundle, "Goal") as unknown as GoalResource[];
  const status = (carePlan.status as string) ?? "draft";
  const patientRef = (carePlan.subject as { display?: string })?.display ?? "Unknown patient";
  const activities = ((carePlan.activity ?? []) as ActivityResource[]);
  const conflicts = ((carePlan.extension ?? []) as Array<{ url?: string; valueString?: string }>)
    .filter((e) => e.url?.includes("conflict"))
    .map((e): Conflict => {
      try {
        return JSON.parse(e.valueString ?? "{}");
      } catch {
        return { description: e.valueString ?? "", cpgs: [], recommendations: [] };
      }
    });

  const provenances = getResources(fhirBundle, "Provenance");
  const devices = getResources(fhirBundle, "Device");
  const isDraft = status === "draft";

  const handleStatusChange = () => {
    setRefreshKey((k) => k + 1);
    setApproveOpen(false);
    setRejectOpen(false);
  };

  return (
    <>
      <PageSection>
        <Flex
          direction={{ default: "row" }}
          alignItems={{ default: "alignItemsCenter" }}
          justifyContent={{ default: "justifyContentSpaceBetween" }}
        >
          <FlexItem>
            <Title headingLevel="h1">Care Plan Review</Title>
            <Flex gap={{ default: "gapSm" }} alignItems={{ default: "alignItemsCenter" }}>
              <FlexItem>Patient: {patientRef}</FlexItem>
              <FlexItem>
                <Label color={statusColor[status] ?? "blue"}>{status}</Label>
              </FlexItem>
            </Flex>
          </FlexItem>
          {isDraft && (
            <FlexItem>
              <Flex gap={{ default: "gapSm" }}>
                <FlexItem>
                  <Button variant="primary" onClick={() => setApproveOpen(true)}>
                    Approve
                  </Button>
                </FlexItem>
                <FlexItem>
                  <Button variant="danger" onClick={() => setRejectOpen(true)}>
                    Reject
                  </Button>
                </FlexItem>
              </Flex>
            </FlexItem>
          )}
        </Flex>
      </PageSection>

      <PageSection isFilled>
        <Tabs activeKey={activeTab} onSelect={(_e, key) => setActiveTab(key as number)}>
          <Tab eventKey={0} title={<TabTitleText>Goals ({goals.length})</TabTitleText>}>
            <Stack hasGutter style={{ paddingTop: "1rem" }}>
              {goals.length === 0 ? (
                <StackItem><p>No goals defined.</p></StackItem>
              ) : (
                goals.map((g, i) => <StackItem key={i}><GoalCard goal={g} /></StackItem>)
              )}
            </Stack>
          </Tab>

          <Tab eventKey={1} title={<TabTitleText>Activities ({activities.length})</TabTitleText>}>
            <Stack hasGutter style={{ paddingTop: "1rem" }}>
              {activities.length === 0 ? (
                <StackItem><p>No activities defined.</p></StackItem>
              ) : (
                activities.map((a, i) => <StackItem key={i}><ActivityCard activity={a} /></StackItem>)
              )}
            </Stack>
          </Tab>

          <Tab eventKey={2} title={<TabTitleText>AI Info</TabTitleText>}>
            <div style={{ paddingTop: "1rem" }}>
              <DescriptionList isHorizontal>
                {devices.map((d, i) => (
                  <DescriptionListGroup key={i}>
                    <DescriptionListTerm>AI Device</DescriptionListTerm>
                    <DescriptionListDescription>
                      {(d.deviceName as Array<{ name: string }>)?.[0]?.name ?? "Unknown model"}
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                ))}
                <DescriptionListGroup>
                  <DescriptionListTerm>Provenance records</DescriptionListTerm>
                  <DescriptionListDescription>{provenances.length}</DescriptionListDescription>
                </DescriptionListGroup>
                <DescriptionListGroup>
                  <DescriptionListTerm>AI Status</DescriptionListTerm>
                  <DescriptionListDescription>
                    <Label color={status === "active" ? "green" : "blue"}>
                      {status === "active" ? "CLINAST_AIRPT" : "AIAST"}
                    </Label>
                  </DescriptionListDescription>
                </DescriptionListGroup>
              </DescriptionList>
            </div>
          </Tab>

          <Tab eventKey={3} title={<TabTitleText>Conflicts ({conflicts.length})</TabTitleText>}>
            <Stack hasGutter style={{ paddingTop: "1rem" }}>
              {conflicts.length === 0 ? (
                <StackItem><p>No conflicts detected.</p></StackItem>
              ) : (
                conflicts.map((c, i) => <StackItem key={i}><ConflictAlert conflict={c} /></StackItem>)
              )}
            </Stack>
          </Tab>
        </Tabs>

        <div style={{ marginTop: "1rem" }}>
          <FhirJsonViewer json={fhirBundle} title="View FHIR Bundle JSON" />
        </div>
      </PageSection>

      <ApprovalDialog
        careplanId={id!}
        isOpen={approveOpen}
        onClose={() => setApproveOpen(false)}
        onApproved={handleStatusChange}
      />
      <RejectionDialog
        careplanId={id!}
        isOpen={rejectOpen}
        onClose={() => setRejectOpen(false)}
        onRejected={handleStatusChange}
      />
    </>
  );
}
