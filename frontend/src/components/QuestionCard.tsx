import { ArrowRight } from "lucide-react";
import type { Question } from "../types";
import FailureBadge from "./FailureBadge";

interface QuestionCardProps {
  question: Question;
  onViewDetails: () => void;
}

export default function QuestionCard({ question, onViewDetails }: QuestionCardProps) {
  const topArticle = question.retrieved[0];

  return (
    <div className="flex flex-col rounded-3xl border border-blush-200/70 bg-white p-6 shadow-soft transition-all hover:-translate-y-0.5 hover:shadow-card">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-display text-2xl font-medium leading-none text-ink">
            {question.frequency.toLocaleString()}
            <span className="ml-1.5 font-sans text-xs font-normal text-ink-muted">
              {question.frequency === 1 ? "time asked" : "times asked"}
            </span>
          </p>
        </div>
        <FailureBadge failureType={question.failureType} />
      </div>

      <h3 className="line-clamp-2 font-medium text-ink">“{question.canonical}”</h3>

      {question.reason && (
        <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-ink-muted">{question.reason}</p>
      )}

      <div className="mt-auto pt-5">
        <div className="flex items-center justify-between gap-3 border-t border-blush-100 pt-4">
          <span className="min-w-0 truncate text-xs text-ink-muted">
            {topArticle ? <>Closest article: {topArticle.title}</> : "No article retrieved"}
          </span>

          <button
            type="button"
            onClick={onViewDetails}
            className="group flex shrink-0 items-center gap-1 text-sm font-medium text-blush-600 transition-colors hover:text-blush-700"
          >
            View details
            <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
