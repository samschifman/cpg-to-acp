import { useCallback, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Button,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Label,
  PageSection,
  Tab,
  Tabs,
  TabTitleText,
  Title,
} from "@patternfly/react-core";
import { FhirJsonViewer, useAdaptivePolling } from "@cpg-to-acp/ui-shared";
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
    <PageSection>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <Title headingLevel="h1">Care Plan Review</Title>
          <span>
            Patient: {patientRef} |{" "}
            <Label color={statusColor[status] ?? "blue"}>{status}</Label>
          </span>
        </div>
        {isDraft && (
          <div>
            <Button variant="primary" onClick={() => setApproveOpen(true)} style={{ marginRight: "0.5rem" }}>
              Approve
            </Button>
            <Button variant="danger" onClick={() => setRejectOpen(true)}>
              Reject
            </Button>
          </div>
        )}
      </div>

      <Tabs activeKey={activeTab} onSelect={(_e, key) => setActiveTab(key as number)}>
        <Tab eventKey={0} title={<TabTitleText>Goals ({goals.length})</TabTitleText>}>
          <PageSection padding={{ default: "noPadding" }}>
            {goals.length === 0 ? (
              <p>No goals defined.</p>
            ) : (
              goals.map((g, i) => <GoalCard key={i} goal={g} />)
            )}
          </PageSection>
        </Tab>

        <Tab eventKey={1} title={<TabTitleText>Activities ({activities.length})</TabTitleText>}>
          <PageSection padding={{ default: "noPadding" }}>
            {activities.length === 0 ? (
              <p>No activities defined.</p>
            ) : (
              activities.map((a, i) => <ActivityCard key={i} activity={a} />)
            )}
          </PageSection>
        </Tab>

        <Tab eventKey={2} title={<TabTitleText>AI Info</TabTitleText>}>
          <PageSection padding={{ default: "noPadding" }}>
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
          </PageSection>
        </Tab>

        <Tab eventKey={3} title={<TabTitleText>Conflicts ({conflicts.length})</TabTitleText>}>
          <PageSection padding={{ default: "noPadding" }}>
            {conflicts.length === 0 ? (
              <p>No conflicts detected.</p>
            ) : (
              conflicts.map((c, i) => <ConflictAlert key={i} conflict={c} />)
            )}
          </PageSection>
        </Tab>
      </Tabs>

      <PageSection padding={{ default: "noPadding" }}>
        <FhirJsonViewer json={fhirBundle} title="View FHIR Bundle JSON" />
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
    </PageSection>
  );
}
