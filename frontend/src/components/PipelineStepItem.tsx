import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Check } from "lucide-react";
import type { PipelineStepInfo } from "../types";

interface PipelineStepItemProps {
  step: PipelineStepInfo;
  isLast: boolean;
}

export default function PipelineStepItem({ step, isLast }: PipelineStepItemProps) {
  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <StatusIcon status={step.status} />
        {!isLast && (
          <div
            className={`mt-1 w-px flex-1 ${
              step.status === "completed" ? "bg-sage-500/50" : "bg-blush-200"
            }`}
          />
        )}
      </div>

      <div className="pb-7">
        <p
          className={`text-sm font-medium ${
            step.status === "pending" ? "text-ink-faint" : step.status === "failed" ? "text-blush-700" : "text-ink"
          }`}
        >
          {step.label}
        </p>
      </div>
    </div>
  );
}

function StatusIcon({ status }: { status: PipelineStepInfo["status"] }) {
  if (status === "completed") {
    return (
      <AnimatePresence mode="wait">
        <motion.div
          key="completed"
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="flex h-6 w-6 items-center justify-center rounded-full bg-sage-500 text-white"
        >
          <Check className="h-3.5 w-3.5" strokeWidth={3} />
        </motion.div>
      </AnimatePresence>
    );
  }

  if (status === "failed") {
    return (
      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-blush-100 text-blush-700">
        <AlertTriangle className="h-3.5 w-3.5" strokeWidth={2.25} />
      </div>
    );
  }

  if (status === "running") {
    return (
      <span className="relative flex h-6 w-6 items-center justify-center">
        <motion.span
          animate={{ scale: [1, 1.6], opacity: [0.5, 0] }}
          transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
          className="absolute h-3 w-3 rounded-full bg-blush-500"
        />
        <span className="relative h-3 w-3 rounded-full bg-blush-500" />
      </span>
    );
  }

  // pending
  return <span className="h-6 w-6 rounded-full border-2 border-blush-200 bg-white" />;
}
