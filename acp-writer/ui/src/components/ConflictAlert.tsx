import { Alert, type AlertProps } from "@patternfly/react-core";
import type { PlanConflict } from "@app/api/models";

const severityToVariant: Record<string, AlertProps["variant"]> = {
  info: "info",
  warning: "warning",
  critical: "danger",
};

const categoryToTitle: Record<string, string> = {
  overlap: "Overlapping activities — consider combining",
  contradiction: "Conflicting recommendations",
  divergent_target: "Conflicting goal targets",
  divergent_schedule: "Conflicting schedules",
  other: "Recommendation conflict",
};

export function ConflictAlert({ conflict }: { conflict: PlanConflict }) {
  const variant = severityToVariant[conflict.severity ?? "warning"] ?? "warning";
  const title = categoryToTitle[conflict.category ?? "other"] ?? "Recommendation conflict";
  // De-duplicate source CPGs for the "From:" line (multiple recs may cite one CPG).
  const cpgs = Array.from(new Set((conflict.sources ?? []).map((s) => s.cpgId)));

  return (
    <Alert variant={variant} isInline title={title}>
      <p>{conflict.description}</p>
      {cpgs.length > 0 && (
        <p>
          <b>From:</b> {cpgs.join(" · ")}
        </p>
      )}
    </Alert>
  );
}
