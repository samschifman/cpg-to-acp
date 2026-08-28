import { useEffect, useState } from "react";
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
  // Submission lifecycle: editing -> submitting -> submitted. On a failed submit
  // we return to editing and surface `error` so the clinician can retry
  // deliberately. Once submitted, the buttons are gone so a duplicate (or
  // changed-decision) submit is impossible; the panel unmounts on its own when a
  // later poll sees the run leave the gate, and remounts fresh when the round
  // advances (RunDetailPage keys it by reviewIteration).
  const [phase, setPhase] = useState<"editing" | "submitting" | "submitted">("editing");
  const [error, setError] = useState<string | null>(null);
  // Set 30s after entering `submitted` if the run is still at this same gate: the
  // engine may just be slow (healthy consumption is 6-24+s) OR the event was
  // dropped (submitted before the gate armed). We can't tell which, so we offer
  // a neutral retry rather than an alarm. Retry is safe by construction: round-
  // binding makes a duplicate either the first-consumed event or an engine-
  // discarded stale one — never a double-apply, never approval of unseen content.
  const [stalled, setStalled] = useState(false);
  const [lastAction, setLastAction] = useState<ReviewAction | null>(null);

  const goals = carePlan.goals ?? [];
  const activities = carePlan.activities ?? [];
  const conflicts = carePlan.conflicts ?? [];

  const submitting = phase === "submitting";

  const submit = async (action: ReviewAction) => {
    setLastAction(action);
    setError(null);
    setStalled(false);
    setPhase("submitting");
    try {
      await onSubmit(action);
      setPhase("submitted");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit review. Please try again.");
      setPhase("editing");
    }
  };

  useEffect(() => {
    if (phase !== "submitted") return;
    const timer = setTimeout(() => setStalled(true), 30_000);
    return () => clearTimeout(timer);
  }, [phase]);

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
              {stalled ? (
                <Alert
                  variant="info"
                  isInline
                  title="Still waiting on the pipeline… you can retry if this persists."
                  actionLinks={
                    <Button
                      variant="link"
                      isInline
                      onClick={() => lastAction && submit(lastAction)}
                    >
                      Retry
                    </Button>
                  }
                />
              ) : (
                <Alert
                  variant="info"
                  isInline
                  title="Review submitted — waiting for the pipeline to pick it up…"
                  customIcon={<Spinner size="md" />}
                />
              )}
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
                        submit({
                          decision: "approve",
                          clinician: clinician || undefined,
                          reviewRound: reviewIteration,
                        })
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
                          reviewRound: reviewIteration,
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
