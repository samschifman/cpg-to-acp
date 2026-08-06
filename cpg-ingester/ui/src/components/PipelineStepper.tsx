import {
  ProgressStep,
  ProgressStepper,
} from '@patternfly/react-core';
import type { PipelineStep } from '../api/types';

function stepVariant(status: PipelineStep['status']) {
  switch (status) {
    case 'completed': return 'success' as const;
    case 'active': return 'info' as const;
    case 'failed': return 'danger' as const;
    default: return 'pending' as const;
  }
}

function formatDuration(startedAt?: string, completedAt?: string): string {
  if (!startedAt) return '';
  const start = new Date(startedAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}m ${remaining}s`;
}

interface PipelineStepperProps {
  steps: PipelineStep[];
}

export function PipelineStepperComponent({ steps }: PipelineStepperProps) {
  return (
    <ProgressStepper isVertical>
      {steps.map((step) => {
        const duration = formatDuration(step.startedAt, step.completedAt);
        return (
          <ProgressStep
            key={`${step.name}-${step.startedAt ?? ''}`}
            variant={stepVariant(step.status)}
            id={step.name}
            titleId={step.name}
            description={duration || undefined}
            isCurrent={step.status === 'active'}
          >
            {step.name}
          </ProgressStep>
        );
      })}
    </ProgressStepper>
  );
}
