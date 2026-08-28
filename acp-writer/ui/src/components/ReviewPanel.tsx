import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardTitle,
  Flex,
  FlexItem,
  Spinner,
  Stack,
  StackItem,
  TextArea,
  TextInput,
} from "@patternfly/react-core";
import type { CarePlanView, ReviewAction } from "@app/api/models";
import { GoalCard } from "./GoalCard";
import { ActivityCard } from "./ActivityCard";
import { ConflictAlert, orderConflicts } from "./ConflictAlert";

interface ReviewPanelProps {
  carePlan: CarePlanView;
  reviewIteration?: number;
  previousFeedback?: ReviewAction | null;
  onSubmit: (action: ReviewAction) => Promise<void>;
}

export function ReviewPanel({
  carePlan,
  reviewIteration,
  previousFeedback,
  onSubmit,
}: ReviewPanelProps) {
  const [mode, setMode] = useState<"idle" | "changes">("idle");
  const [clinician, setClinician] = useState("");
  const [comment, setComment] = useState("");
  // Submission lifecycle: editing -> submitting -> submitted (terminal). On a
  // failed submit we return to editing and surface `error` so the clinician can
  // retry deliberately. Once submitted, the buttons are gone so a duplicate (or
  // changed-decision) submit is impossible; the panel unmounts on its own when a
  // later poll sees the run leave the review gate.
  const [phase, setPhase] = useState<"editing" | "submitting" | "submitted">("editing");
  const [error, setError] = useState<string | null>(null);

  const goals = carePlan.goals ?? [];
  const activities = carePlan.activities ?? [];
  const conflicts = carePlan.conflicts ?? [];

  const submitting = phase === "submitting";

  const submit = async (action: ReviewAction) => {
    setError(null);
    setPhase("submitting");
    try {
      await onSubmit(action);
      setPhase("submitted");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit review. Please try again.");
      setPhase("editing");
    }
  };

  return (
    <Card>
      <CardTitle>
        Care-plan review{typeof reviewIteration === "number" ? ` — round ${reviewIteration + 1}` : ""}
      </CardTitle>
      <CardBody>
        <Stack hasGutter>
          {previousFeedback?.comment && (
            <StackItem>
              <em>Previously requested:</em> {previousFeedback.comment}
            </StackItem>
          )}
          {orderConflicts(conflicts).map((c) => (
            <StackItem key={c.id}><ConflictAlert conflict={c} /></StackItem>
          ))}
          <StackItem>
            <strong>Goals ({goals.length})</strong>
            <Stack hasGutter>
              {goals.map((g) => <StackItem key={g.id}><GoalCard goal={g} /></StackItem>)}
            </Stack>
          </StackItem>
          <StackItem>
            <strong>Activities ({activities.length})</strong>
            <Stack hasGutter>
              {activities.map((a) => <StackItem key={a.id}><ActivityCard activity={a} /></StackItem>)}
            </Stack>
          </StackItem>

          {phase === "submitted" ? (
            <StackItem>
              <Alert
                variant="info"
                isInline
                title="Review submitted — waiting for the pipeline to pick it up…"
                customIcon={<Spinner size="md" />}
              />
            </StackItem>
          ) : (
          <>
          {error && (
            <StackItem>
              <Alert variant="danger" isInline title={error} />
            </StackItem>
          )}

          <StackItem>
            <TextInput
              aria-label="Clinician name"
              placeholder="Clinician name"
              value={clinician}
              isDisabled={submitting}
              onChange={(_e, v) => setClinician(v)}
            />
          </StackItem>

          {mode === "changes" && (
            <StackItem>
              <TextArea
                aria-label="Overall comment"
                placeholder="What should change?"
                value={comment}
                isDisabled={submitting}
                onChange={(_e, v) => setComment(v)}
              />
            </StackItem>
          )}

          <StackItem>
            <Flex gap={{ default: "gapSm" }}>
              {mode === "idle" ? (
                <>
                  <FlexItem>
                    <Button
                      variant="primary"
                      isLoading={submitting}
                      isDisabled={submitting}
                      onClick={() =>
                        submit({ decision: "approve", clinician: clinician || undefined })
                      }
                    >
                      Approve
                    </Button>
                  </FlexItem>
                  <FlexItem>
                    <Button
                      variant="secondary"
                      isDisabled={submitting}
                      onClick={() => setMode("changes")}
                    >
                      Request changes
                    </Button>
                  </FlexItem>
                </>
              ) : (
                <>
                  <FlexItem>
                    <Button
                      variant="primary"
                      isLoading={submitting}
                      isDisabled={submitting || !comment.trim()}
                      onClick={() =>
                        submit({
                          decision: "request_changes",
                          clinician: clinician || undefined,
                          comment: comment.trim(),
                        })
                      }
                    >
                      Submit changes
                    </Button>
                  </FlexItem>
                  <FlexItem>
                    <Button variant="link" isDisabled={submitting} onClick={() => setMode("idle")}>
                      Cancel
                    </Button>
                  </FlexItem>
                </>
              )}
            </Flex>
          </StackItem>
          </>
          )}
        </Stack>
      </CardBody>
    </Card>
  );
}
