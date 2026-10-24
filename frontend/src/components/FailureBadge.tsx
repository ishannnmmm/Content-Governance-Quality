import type { FailureType } from "../types";
import { FAILURE_TYPES } from "../utils/failureTypes";

interface FailureBadgeProps {
  failureType: FailureType;
}

export default function FailureBadge({ failureType }: FailureBadgeProps) {
  const style = FAILURE_TYPES[failureType] ?? FAILURE_TYPES.unjudged;

  return (
    <span className={`whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ${style.badge}`}>
      {style.label}
    </span>
  );
}
