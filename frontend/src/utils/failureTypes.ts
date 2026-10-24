import type { FailureType } from "../types";

interface FailureTypeStyle {
  label: string;
  /** Who acts on it — the reason the dashboard splits by failure type. */
  owner: string;
  description: string;
  dot: string;
  badge: string;
}

export const FAILURE_TYPES: Record<FailureType, FailureTypeStyle> = {
  content_gap: {
    label: "Content gap",
    owner: "Article writers",
    description: "No article answers these questions. Something new needs writing.",
    dot: "bg-blush-500",
    badge: "bg-blush-500 text-white",
  },
  retrieval_gap: {
    label: "Retrieval gap",
    owner: "Search config owners",
    description: "The right article exists but search did not surface it.",
    dot: "bg-amber-400",
    badge: "bg-amber-100 text-amber-800",
  },
  clarity_gap: {
    label: "Clarity gap",
    owner: "Authors of the matched articles",
    description: "An article is close, but only partly answers the question as written.",
    dot: "bg-sky-400",
    badge: "bg-sky-100 text-sky-800",
  },
  covered: {
    label: "Covered",
    owner: "No action needed",
    description: "An existing article fully answers these questions.",
    dot: "bg-sage-500",
    badge: "bg-sage-50 text-sage-600",
  },
  unjudged: {
    label: "Not judged",
    owner: "Re-run",
    description: "The judge's response could not be read. These are not counted either way.",
    dot: "bg-ink-faint",
    badge: "bg-blush-50 text-ink-muted",
  },
};

/** Work-queue order: the gaps first, then what is fine, then what failed. */
export const FAILURE_TYPE_ORDER: FailureType[] = [
  "content_gap",
  "retrieval_gap",
  "clarity_gap",
  "covered",
  "unjudged",
];
