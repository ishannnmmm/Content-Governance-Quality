export interface UploadedFile {
  id: string;
  name: string;
  size: number; // bytes
  type: string;
}

export type PipelineStepStatus = "pending" | "running" | "completed" | "failed";

export interface PipelineStepInfo {
  key: string;
  label: string;
  status: PipelineStepStatus;
}

export type PipelineState = "running" | "completed" | "failed";

export interface PipelineStatus {
  jobId: string;
  steps: PipelineStepInfo[];
  /** 0-100, or null when the backend can't report a percentage (renders as indeterminate) */
  progress: number | null;
  elapsedSeconds: number;
  currentStepLabel: string | null;
  state: PipelineState;
  error?: string | null;
}

/**
 * Why a question is not answered. The three gaps go to different owners:
 * content gaps to article writers, retrieval gaps to whoever owns search
 * config, clarity gaps back to the authors of the specific articles.
 */
export type FailureType = "content_gap" | "retrieval_gap" | "clarity_gap" | "covered" | "unjudged";

export type CoverageVerdict = "fully" | "partially" | "not" | "error";

export interface RetrievedArticle {
  articleId: string;
  title: string;
  /** Cross-encoder score — unbounded, higher is more relevant. Not a probability. */
  score: number;
}

export interface Routing {
  flow: string;
  verdict: "correct" | "misrouted" | "no_flow_fits" | "error";
  reason?: string | null;
}

/** Counts per outcome. null means the export had no data for it. */
export interface Outcomes {
  selfServed: number | null;
  abandoned: number | null;
  escalated: number | null;
}

export interface Question {
  id: string;
  canonical: string;
  /** How many times this question (in any phrasing) was asked. */
  frequency: number;
  variants: string[];
  failureType: FailureType;
  verdict: CoverageVerdict;
  reason: string | null;
  /** What an article would need to say to answer it. */
  requiredContent: string | null;
  retrieved: RetrievedArticle[];
  /** null when the export has no routed-intent data. */
  routing: Routing | null;
  outcomes: Outcomes;
}

export interface AnalysisSummary {
  totalQuestions: number;
  distinctQuestions: number;
  answerablePercent: number;
  contentGaps: number;
  /** null when no labelled set was available to measure retrieval against. */
  retrievalGaps: number | null;
  clarityGaps: number;
  unjudged: number;
}

export interface AnalysisResult {
  jobId: string;
  generatedAt: string;
  summary: AnalysisSummary;
  /** Ranked by frequency. */
  questions: Question[];
}

export type AppStage = "welcome" | "processing" | "results" | "error";
