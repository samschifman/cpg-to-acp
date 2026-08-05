import { Alert } from "@patternfly/react-core";

export interface Conflict {
  description: string;
  cpgs: string[];
  recommendations: string[];
}

export function ConflictAlert({ conflict }: { conflict: Conflict }) {
  return (
    <Alert variant="warning" isInline title="Overlapping Recommendation">
      <p>{conflict.description}</p>
      <p>
        <strong>Guidelines:</strong> {conflict.cpgs.join(", ")}
      </p>
      <p>
        <strong>Recommendations:</strong> {conflict.recommendations.join(", ")}
      </p>
    </Alert>
  );
}
