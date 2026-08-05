import { useState } from "react";
import {
  Button,
  Form,
  FormGroup,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  TextArea,
} from "@patternfly/react-core";
import { updateCarePlanStatus } from "@app/services/api";

interface RejectionDialogProps {
  careplanId: string;
  isOpen: boolean;
  onClose: () => void;
  onRejected: () => void;
}

export function RejectionDialog({
  careplanId,
  isOpen,
  onClose,
  onRejected,
}: RejectionDialogProps) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleReject = async () => {
    if (!reason.trim()) return;
    setSubmitting(true);
    try {
      await updateCarePlanStatus(careplanId, {
        status: "entered-in-error",
        reason,
      });
      onRejected();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="small">
      <ModalHeader title="Reject Care Plan" />
      <ModalBody>
        <Form>
          <FormGroup label="Reason (required)" fieldId="reject-reason" isRequired>
            <TextArea
              id="reject-reason"
              value={reason}
              onChange={(_e, val) => setReason(val)}
              placeholder="Explain why this care plan is being rejected"
              isRequired
            />
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="danger"
          onClick={handleReject}
          isLoading={submitting}
          isDisabled={submitting || !reason.trim()}
        >
          Reject
        </Button>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  );
}
