import { useState } from "react";
import {
  Button,
  Form,
  FormGroup,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  TextInput,
} from "@patternfly/react-core";
import { updateCarePlanStatus } from "@app/services/api";

interface ApprovalDialogProps {
  careplanId: string;
  isOpen: boolean;
  onClose: () => void;
  onApproved: () => void;
}

export function ApprovalDialog({
  careplanId,
  isOpen,
  onClose,
  onApproved,
}: ApprovalDialogProps) {
  const [clinician, setClinician] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleApprove = async () => {
    setSubmitting(true);
    try {
      await updateCarePlanStatus(careplanId, {
        status: "active",
        clinician: clinician || undefined,
      });
      onApproved();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="small">
      <ModalHeader title="Approve Care Plan" />
      <ModalBody>
        <Form>
          <FormGroup label="Clinician name" fieldId="clinician-name">
            <TextInput
              id="clinician-name"
              value={clinician}
              onChange={(_e, val) => setClinician(val)}
              placeholder="Dr. Smith"
            />
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          onClick={handleApprove}
          isLoading={submitting}
          isDisabled={submitting}
        >
          Approve
        </Button>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  );
}
