import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FileText, MessageSquare, PenLine, X } from "lucide-react";
import type { Question } from "../types";
import { FAILURE_TYPES } from "../utils/failureTypes";
import FailureBadge from "./FailureBadge";

interface QuestionDetailsProps {
  question: Question | null;
  onClose: () => void;
}

type Tab = "variants" | "retrieved" | "missing";

const ROUTING_LABELS: Record<string, string> = {
  correct: "Routed correctly",
  misrouted: "Misrouted",
  no_flow_fits: "No flow fits",
  error: "Not judged",
};

export default function QuestionDetails({ question, onClose }: QuestionDetailsProps) {
  const [tab, setTab] = useState<Tab>("variants");

  useEffect(() => {
    if (question) setTab(question.failureType === "covered" ? "retrieved" : "missing");
  }, [question]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <AnimatePresence>
      {question && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-ink/30 backdrop-blur-[2px]"
          />

          <motion.div
            key="panel"
            role="dialog"
            aria-modal="true"
            aria-label="Question details"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between gap-4 border-b border-blush-100 px-7 pb-5 pt-7">
              <div className="min-w-0">
                <div className="mb-2 flex items-center gap-2">
                  <FailureBadge failureType={question.failureType} />
                  <span className="text-xs text-ink-muted">{FAILURE_TYPES[question.failureType].owner}</span>
                </div>
                <h2 className="font-display text-xl font-medium text-ink">“{question.canonical}”</h2>
                <p className="mt-1 text-sm text-ink-muted">
                  Asked {question.frequency.toLocaleString()} {question.frequency === 1 ? "time" : "times"}
                  {question.variants.length > 1 && ` in ${question.variants.length} phrasings`}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close details"
                className="rounded-full p-2 text-ink-muted transition-colors hover:bg-blush-50 hover:text-ink"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="flex gap-5 border-b border-blush-100 px-7 pt-4">
              <TabButton label="Variants" active={tab === "variants"} onClick={() => setTab("variants")} />
              <TabButton
                label="Retrieved articles"
                active={tab === "retrieved"}
                onClick={() => setTab("retrieved")}
              />
              <TabButton label="What's missing" active={tab === "missing"} onClick={() => setTab("missing")} />
            </div>

            <div className="flex-1 overflow-y-auto px-7 py-6">
              {tab === "variants" && <VariantsTab question={question} />}
              {tab === "retrieved" && <RetrievedTab question={question} />}
              {tab === "missing" && <MissingTab question={question} />}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative pb-3 text-sm font-medium transition-colors ${
        active ? "text-ink" : "text-ink-muted hover:text-ink"
      }`}
    >
      {label}
      {active && <span className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-blush-500" />}
    </button>
  );
}

function VariantsTab({ question }: { question: Question }) {
  return (
    <div className="space-y-3">
      <p className="mb-1 text-xs text-ink-faint">
        Different ways customers phrased this question. Names, emails, phone numbers and account
        numbers are removed before these are shown.
      </p>
      {question.variants.map((variant, i) => (
        <div key={`${i}-${variant}`} className="flex items-start gap-2.5 rounded-2xl bg-blush-50 p-4">
          <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" />
          <p className="text-sm leading-relaxed text-ink">{variant}</p>
        </div>
      ))}
      <OutcomesBlock question={question} />
    </div>
  );
}

function OutcomesBlock({ question }: { question: Question }) {
  const { selfServed, abandoned, escalated } = question.outcomes;
  const show = (n: number | null) => (n === null ? "—" : n.toLocaleString());

  return (
    <div className="pt-3">
      <p className="mb-2 text-sm font-medium text-ink">What happened next</p>
      <div className="grid grid-cols-3 gap-3">
        <StatRow label="Self-served" value={show(selfServed)} />
        <StatRow label="Abandoned" value={show(abandoned)} />
        <StatRow label="Escalated" value={show(escalated)} />
      </div>
      {(selfServed === null || abandoned === null) && (
        <p className="mt-2 text-xs text-ink-faint">— this export has no outcome data beyond escalation.</p>
      )}
    </div>
  );
}

function RetrievedTab({ question }: { question: Question }) {
  if (question.retrieved.length === 0) {
    return <p className="text-sm text-ink-muted">Search returned no articles for this question.</p>;
  }

  return (
    <div className="space-y-3">
      <p className="mb-1 text-xs text-ink-faint">
        Ranked by the reranker. Scores are relative relevance, not probabilities — compare them
        within a question, not across questions.
      </p>
      {question.retrieved.map((article, i) => (
        <div key={article.articleId} className="flex items-start gap-3 rounded-2xl bg-blush-50 p-4">
          <FileText className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-ink">{article.title}</p>
            <p className="mt-0.5 text-xs text-ink-muted">
              {article.articleId} · score {article.score.toFixed(2)}
              {i === 0 && " · top match"}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function MissingTab({ question }: { question: Question }) {
  return (
    <div className="space-y-6">
      <div>
        <p className="mb-2 text-sm font-medium text-ink">Judge's verdict</p>
        <p className="text-sm leading-relaxed text-ink-muted">
          <span className="font-medium capitalize text-ink">{question.verdict}</span>
          {question.verdict !== "error" && " covered by the best article"}
          {question.reason && <> — {question.reason}</>}
        </p>
      </div>

      <div>
        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-ink">
          <PenLine className="h-4 w-4 text-blush-500" />
          What an article would need to say
        </div>
        <p className="rounded-2xl bg-blush-50 p-4 text-sm leading-relaxed text-ink">
          {question.requiredContent ?? "Nothing — an existing article already answers this."}
        </p>
      </div>

      {question.routing && (
        <div>
          <p className="mb-2 text-sm font-medium text-ink">Bot routing</p>
          <div className="grid grid-cols-2 gap-3">
            <StatRow label="Routed to" value={question.routing.flow} />
            <StatRow label="Verdict" value={ROUTING_LABELS[question.routing.verdict] ?? question.routing.verdict} />
          </div>
          {question.routing.reason && (
            <p className="mt-2 text-xs leading-relaxed text-ink-muted">{question.routing.reason}</p>
          )}
        </div>
      )}
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-blush-50 px-4 py-3">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="mt-0.5 truncate font-medium text-ink">{value}</p>
    </div>
  );
}
