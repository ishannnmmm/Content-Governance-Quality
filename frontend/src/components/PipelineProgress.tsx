import { motion } from "framer-motion";
import type { PipelineStatus } from "../types";
import { formatElapsed } from "../utils/format";
import PipelineStepItem from "./PipelineStepItem";

interface PipelineProgressProps {
  status: PipelineStatus;
}

export default function PipelineProgress({ status }: PipelineProgressProps) {
  const hasDeterminateProgress = status.progress !== null;

  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-16">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="w-full max-w-lg"
      >
        <div className="mb-8 text-center">
          <h1 className="font-display text-3xl font-medium text-ink">Analyzing your conversations…</h1>
          <p className="mt-2 text-sm text-ink-muted">
            {status.currentStepLabel ? `Currently: ${status.currentStepLabel}` : "Wrapping up"}
          </p>
        </div>

        <div className="rounded-[1.75rem] bg-white p-7 shadow-soft">
          <div className="mb-7 flex items-center justify-between">
            <span className="font-mono text-sm text-ink-muted">{formatElapsed(status.elapsedSeconds)} elapsed</span>
            {hasDeterminateProgress && (
              <span className="text-sm font-medium text-blush-600">{status.progress}%</span>
            )}
          </div>

          <div className="mb-8 h-2 w-full overflow-hidden rounded-full bg-blush-100">
            {hasDeterminateProgress ? (
              <motion.div
                className="h-full rounded-full bg-blush-500"
                animate={{ width: `${status.progress}%` }}
                transition={{ duration: 0.4, ease: "easeOut" }}
              />
            ) : (
              <div className="relative h-full w-full">
                <div className="absolute inset-y-0 w-1/3 animate-indeterminate rounded-full bg-blush-500" />
              </div>
            )}
          </div>

          <div>
            {status.steps.map((step, i) => (
              <PipelineStepItem key={step.key} step={step} isLast={i === status.steps.length - 1} />
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
