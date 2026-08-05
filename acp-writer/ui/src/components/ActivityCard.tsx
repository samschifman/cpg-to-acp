import {
  Card,
  CardBody,
  CardTitle,
  ExpandableSection,
  Label,
} from "@patternfly/react-core";
import {
  HeartbeatIcon,
  RunningIcon,
} from "@patternfly/react-icons";

export interface ActivityResource {
  detail?: {
    description?: string;
    kind?: string;
    status?: string;
  };
  reference?: {
    display?: string;
    reference?: string;
  };
  extension?: Array<{
    url?: string;
    valueString?: string;
    valueCode?: string;
  }>;
}

function activityIcon(kind?: string) {
  switch (kind?.toLowerCase()) {
    case "medicationrequest":
      return "💊";
    case "servicerequest":
      return <HeartbeatIcon />;
    default:
      return <RunningIcon />;
  }
}

function getExtensionValue(
  extensions: ActivityResource["extension"],
  urlFragment: string,
): string | undefined {
  return extensions?.find((e) => e.url?.includes(urlFragment))?.valueString;
}

export function ActivityCard({ activity }: { activity: ActivityResource }) {
  const description =
    activity.detail?.description ??
    activity.reference?.display ??
    "Activity";
  const kind = activity.detail?.kind;
  const source = getExtensionValue(activity.extension, "source-cpg");
  const section = getExtensionValue(activity.extension, "source-section");
  const strength = getExtensionValue(activity.extension, "recommendation-strength");
  const rationale = getExtensionValue(activity.extension, "rationale");
  const isAiGenerated = activity.extension?.some((e) =>
    e.url?.includes("ai-generated"),
  );

  return (
    <Card isCompact>
      <CardTitle>
        <span style={{ marginRight: "0.5rem" }}>{activityIcon(kind)}</span>
        {description}
      </CardTitle>
      <CardBody>
        {source && (
          <span style={{ marginRight: "0.5rem" }}>
            Source: {source}
            {section ? ` §${section}` : ""}
          </span>
        )}
        {strength && (
          <Label isCompact color="blue">
            {strength}
          </Label>
        )}{" "}
        {isAiGenerated && (
          <Label isCompact color="orange">
            AI-generated
          </Label>
        )}
        {rationale && (
          <ExpandableSection toggleText="Rationale" isIndented>
            {rationale}
          </ExpandableSection>
        )}
      </CardBody>
    </Card>
  );
}
