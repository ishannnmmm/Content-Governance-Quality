import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import type { AnalysisResult, FailureType, Question } from "../types";
import { FAILURE_TYPES, FAILURE_TYPE_ORDER } from "../utils/failureTypes";
import SummaryCard from "./SummaryCard";
import QuestionCard from "./QuestionCard";
import QuestionDetails from "./QuestionDetails";
import CoverageBar from "./CoverageBar";

interface ResultsDashboardProps {
  result: AnalysisResult;
}

const PAGE_SIZE = 20;

export default function ResultsDashboard({ result }: ResultsDashboardProps) {
  const [selectedQuestion, setSelectedQuestion] = useState<Question | null>(null);

  // Group by failure type, not by topic — each group is a separate work
  // queue with its own owner. Order within a group stays by frequency,
  // which the backend has already ranked.
  const groups = useMemo(() => {
    const byType = Object.fromEntries(FAILURE_TYPE_ORDER.map((t) => [t, [] as Question[]])) as Record<
      FailureType,
      Question[]
    >;
    for (const q of result.questions) (byType[q.failureType] ?? byType.unjudged).push(q);
    return byType;
  }, [result.questions]);

  const counts = Object.fromEntries(FAILURE_TYPE_ORDER.map((t) => [t, groups[t].length])) as Record<
    FailureType,
    number
  >;

  const firstWithItems = FAILURE_TYPE_ORDER.find((t) => counts[t] > 0) ?? "content_gap";
  const [activeType, setActiveType] = useState<FailureType>(firstWithItems);
  const [visible, setVisible] = useState(PAGE_SIZE);

  const { summary } = result;
  const active = groups[activeType];

  function selectType(type: FailureType) {
    setActiveType(type);
    setVisible(PAGE_SIZE);
  }

  return (
    <div className="min-h-screen px-6 py-16">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="mx-auto max-w-5xl"
      >
        <h1 className="font-display text-3xl font-medium text-ink sm:text-4xl">
          Your knowledge base evaluation is ready ✨
        </h1>
        <p className="mt-2 text-sm text-ink-muted">
          {summary.totalQuestions.toLocaleString()} customer questions, grouped into{" "}
          {summary.distinctQuestions.toLocaleString()} distinct ones and checked against your articles.
        </p>

        <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <SummaryCard label="Questions asked" value={summary.totalQuestions.toLocaleString()} />
          <SummaryCard label="Distinct questions" value={summary.distinctQuestions.toLocaleString()} />
          <SummaryCard label="Answerable" value={`${Math.round(summary.answerablePercent)}%`} />
          <SummaryCard
            label="Gaps to fix"
            value={(summary.contentGaps + (summary.retrievalGaps ?? 0) + summary.clarityGaps).toLocaleString()}
          />
        </div>

        <div className="mt-6 rounded-3xl border border-blush-200/70 bg-white p-6 shadow-soft">
          <p className="mb-3 text-sm font-medium text-ink">Distinct questions by outcome</p>
          <CoverageBar counts={counts} showLegend />
          {summary.retrievalGaps === null && (
            <p className="mt-3 text-xs text-ink-faint">
              Retrieval gaps weren't measured — that needs a labelled set of questions with known
              answering articles. Until then, some content gaps may really be retrieval gaps.
            </p>
          )}
        </div>

        <div className="mt-12">
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Failure type">
            {FAILURE_TYPE_ORDER.filter((t) => t !== "unjudged" || counts.unjudged > 0).map((type) => (
              <button
                key={type}
                type="button"
                role="tab"
                aria-selected={activeType === type}
                onClick={() => selectType(type)}
                className={`flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-colors ${
                  activeType === type
                    ? "border-ink bg-ink text-white"
                    : "border-blush-200 bg-white text-ink-muted hover:text-ink"
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${FAILURE_TYPES[type].dot}`} />
                {FAILURE_TYPES[type].label}
                <span className={activeType === type ? "text-white/70" : "text-ink-faint"}>
                  {type === "retrieval_gap" && summary.retrievalGaps === null ? "—" : counts[type]}
                </span>
              </button>
            ))}
          </div>

          <p className="mt-4 text-sm text-ink-muted">
            {FAILURE_TYPES[activeType].description}{" "}
            <span className="text-ink-faint">Owner: {FAILURE_TYPES[activeType].owner}.</span>
          </p>

          {active.length === 0 ? (
            <p className="mt-6 rounded-3xl bg-blush-50 px-6 py-8 text-center text-sm text-ink-muted">
              No questions in this group.
            </p>
          ) : (
            <>
              <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
                {active.slice(0, visible).map((question) => (
                  <QuestionCard
                    key={question.id}
                    question={question}
                    onViewDetails={() => setSelectedQuestion(question)}
                  />
                ))}
              </div>
              {active.length > visible && (
                <div className="mt-6 text-center">
                  <button
                    type="button"
                    onClick={() => setVisible((v) => v + PAGE_SIZE)}
                    className="rounded-full border border-blush-200 bg-white px-5 py-2 text-sm font-medium text-ink-muted transition-colors hover:text-ink"
                  >
                    Show more ({(active.length - visible).toLocaleString()} left)
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </motion.div>

      <QuestionDetails question={selectedQuestion} onClose={() => setSelectedQuestion(null)} />
    </div>
  );
}
