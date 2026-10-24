"""
eval_config.py
━━━━━━━━━━━━━━
Tuning constants for the KB evaluation pipeline, kept in one place
because they will be adjusted repeatedly while retrieval and the judge
are calibrated. Every value can be overridden with an env var of the
same name.
"""

import os


def _env(name, default, cast=str):
    raw = os.environ.get(name)
    return default if raw is None or raw == "" else cast(raw)


# Cross-encoder scores are unbounded, not probabilities. Starts at zero
# deliberately — set it from the distribution observed on known-good and
# known-bad pairs after the first full run, not from a guess.
RETRIEVAL_FLOOR = _env("RETRIEVAL_FLOOR", 0.0, float)

# Reciprocal rank fusion constant. Standard; rarely needs changing.
RRF_K = _env("RRF_K", 60, int)

# Articles retrieved (dense + BM25, fused) before reranking.
CANDIDATES = _env("CANDIDATES", 20, int)

# Articles kept after reranking and passed to the judge.
TOP_K = _env("TOP_K", 5, int)

# Of those, how many the judge reads per question (in rank order, stopping
# at the first "fully"). Each is one LLM call, so this multiplies run time.
JUDGE_TOP_K = _env("JUDGE_TOP_K", 3, int)

# Cosine distance for grouping phrasings into one canonical question.
# Lower groups less aggressively.
DEDUPE_THRESHOLD = _env("DEDUPE_THRESHOLD", 0.15, float)

JUDGE_MODEL = _env("JUDGE_MODEL", "openai/gpt-oss-120b")

# Concurrent judge calls. Raise carefully against Groq rate limits.
JUDGE_CONCURRENCY = _env("JUDGE_CONCURRENCY", 5, int)

EMBED_MODEL = _env("EMBED_MODEL", "all-MiniLM-L6-v2")
RERANK_MODEL = _env("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# KB column names. Step 0 exists because a mismatch here silently
# produced "100% not covered" — map your file's headers onto these.
KB_ID_COL = _env("KB_ID_COL", "article_id")
KB_TITLE_COL = _env("KB_TITLE_COL", "title")
KB_TEXT_COL = _env("KB_TEXT_COL", "content")

# Bot-flow column names.
FLOW_NAME_COL = _env("FLOW_NAME_COL", "intent_name")
FLOW_DESC_COL = _env("FLOW_DESC_COL", "description")
FLOW_PHRASES_COL = _env("FLOW_PHRASES_COL", "training_phrases")
