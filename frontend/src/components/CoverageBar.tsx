import type { FailureType } from "../types";
import { FAILURE_TYPES, FAILURE_TYPE_ORDER } from "../utils/failureTypes";

interface CoverageBarProps {
  /** Distinct questions per failure type across the whole run. */
  counts: Partial<Record<FailureType, number>>;
  showLegend?: boolean;
}

export default function CoverageBar({ counts, showLegend = false }: CoverageBarProps) {
  const segments = FAILURE_TYPE_ORDER.map((type) => ({ type, count: counts[type] ?? 0 }));
  const total = segments.reduce((sum, s) => sum + s.count, 0) || 1;

  return (
    <div>
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-blush-100"
        role="img"
        aria-label={segments
          .filter((s) => s.count > 0)
          .map((s) => `${s.count} ${FAILURE_TYPES[s.type].label.toLowerCase()}`)
          .join(", ")}
      >
        {segments.map(({ type, count }) => {
          const width = (count / total) * 100;
          if (width <= 0) return null;
          return <div key={type} className={FAILURE_TYPES[type].dot} style={{ width: `${width}%` }} />;
        })}
      </div>

      {showLegend && (
        <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1">
          {segments
            .filter(({ type, count }) => count > 0 || type !== "unjudged")
            .map(({ type, count }) => (
              <span key={type} className="flex items-center gap-1.5 text-xs text-ink-muted">
                <span className={`h-2 w-2 rounded-full ${FAILURE_TYPES[type].dot}`} />
                {FAILURE_TYPES[type].label} {count.toLocaleString()}
              </span>
            ))}
        </div>
      )}
    </div>
  );
}
