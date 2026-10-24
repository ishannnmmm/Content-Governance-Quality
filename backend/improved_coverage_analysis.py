"""
improved_coverage_analysis.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage 2 — KB evaluation.

Replaces the old similarity-threshold coverage audit. Cosine similarity
is no longer a verdict: it is one half of retrieval, and an LLM judge
decides whether the retrieved article actually answers the question.

    extract questions → deduplicate into canonical questions with counts
    → retrieve candidate articles → rerank → judge → classify failure
    → rank by frequency

Every LLM call goes through llm_client.ask(), which scrubs PII.

Outputs (in OUTPUT_DIR):
    question_evaluation.json  — one record per canonical question
    question_evaluation.csv   — same, flattened for spreadsheets

CLI:
    python improved_coverage_analysis.py questions.csv kb_articles.csv bot_flows.csv out_dir
"""

import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from canonical import canonicalise
from eval_config import (
    FLOW_DESC_COL, FLOW_NAME_COL, FLOW_PHRASES_COL, JUDGE_CONCURRENCY, JUDGE_TOP_K,
    RETRIEVAL_FLOOR, TOP_K,
)
from judge import classify_failure, judge_coverage, judge_routing
from metrics import load_labelled_set, normalise_question, retrieval_gaps

_VERDICT_RANK = {"fully": 0, "partially": 1, "not": 2, "error": 3}

# One index per KB file per process — building it loads two models and
# encodes every article, so reuse it across jobs until the file changes.
_index_cache: dict = {}


# Speaker-label words that are roles, not people — never scrub these.
_ROLE_WORDS = {"customer", "cust", "agent", "bot", "system", "visitor", "user",
               "virtual", "assistant", "chatbot", "support", "representative"}


# ─────────────────────────────────────────────────────────────
# REFERENCE DATA
# ─────────────────────────────────────────────────────────────

def scrub_denylist(speaker_names: set, kb_file: str) -> set:
    """
    Speaker names to scrub case-insensitively from everything sent to the
    LLM or the UI.

    Two kinds of token are exempt. Role labels ("customer", "agent") are
    not people. Words the KB itself uses are exempt too: a customer named
    Bill must not turn every "bill" in a billing question into [CUSTOMER],
    which would blind the judge on exactly the questions being evaluated.
    "Bill Smith" is still caught by the First-Last pattern.
    """
    names = {n for n in speaker_names if n not in _ROLE_WORDS}
    try:
        from retrieval import load_kb

        kb = load_kb(kb_file)
        vocab = set(
            re.findall(r"[a-z'-]+", " ".join((kb["title"] + " " + kb["content"]).str.lower()))
        )
    except Exception:  # noqa: BLE001 — validation reports a bad KB separately
        vocab = set()
    exempt = names & vocab
    if exempt:
        print(f"  Speaker names also used as KB words, not scrubbed: {', '.join(sorted(exempt))}")
    return names - exempt


def get_index(kb_file: str, embedder=None):
    from retrieval import KBIndex, load_kb

    key = (os.path.abspath(kb_file), os.path.getmtime(kb_file))
    if key not in _index_cache:
        _index_cache.clear()
        _index_cache[key] = KBIndex(load_kb(kb_file), embedder=embedder)
    return _index_cache[key]


def load_flows(path: str) -> dict:
    """flow name (lowercased) → {name, description}. Empty if no file."""
    if not path or not os.path.exists(path):
        return {}
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    lower = {c.lower(): c for c in df.columns}

    def col(name):
        return name if name in df.columns else lower.get(name.lower())

    name_col, desc_col, phrase_col = col(FLOW_NAME_COL), col(FLOW_DESC_COL), col(FLOW_PHRASES_COL)
    if name_col is None:
        print(f"  ⚠️  Bot-flow file has no '{FLOW_NAME_COL}' column — routing will not be judged")
        return {}

    flows = {}
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        description = str(row[desc_col]).strip() if desc_col and pd.notna(row[desc_col]) else ""
        if not description and phrase_col and pd.notna(row[phrase_col]):
            # No description column: the training phrases are the next
            # best statement of what the flow is for.
            description = f"Handles requests like: {str(row[phrase_col])[:400]}"
        flows[name.lower()] = {"name": name, "description": description or "(no description)"}
    return flows


# ─────────────────────────────────────────────────────────────
# STEP — DEDUPLICATE INTO CANONICAL QUESTIONS
# ─────────────────────────────────────────────────────────────

def group_questions(texts: list[str], clean_texts: list[str], embeddings: np.ndarray) -> list[dict]:
    """
    Collapse exact repeats first (cheap, and keeps agglomerative clustering
    small), then group near-identical phrasings with canonicalise().

    Returned groups carry `rows`: positions into `texts`, one per time the
    question was asked, so frequency counts every asking.
    """
    first_row: dict[str, int] = {}
    rows_by_key: dict[str, list[int]] = {}
    for i, t in enumerate(clean_texts):
        key = normalise_question(t)
        if not key:
            continue
        first_row.setdefault(key, i)
        rows_by_key.setdefault(key, []).append(i)

    keys = list(first_row)
    unique_texts = [texts[first_row[k]] for k in keys]
    unique_emb = embeddings[[first_row[k] for k in keys]]

    groups = []
    for g in canonicalise(unique_texts, unique_emb):
        rows = [r for u in g["indices"] for r in rows_by_key[keys[u]]]
        groups.append({
            "canonical": g["canonical"],
            "variants": g["variants"],
            "frequency": len(rows),
            "rows": rows,
        })
    return sorted(groups, key=lambda g: g["frequency"], reverse=True)


# ─────────────────────────────────────────────────────────────
# STEP — RETRIEVE + JUDGE
# ─────────────────────────────────────────────────────────────

def retrieve_all(groups: list[dict], index) -> None:
    for g in groups:
        g["retrieved"] = index.search(g["canonical"], k=TOP_K)


def _judge_one(group: dict, names) -> dict:
    """
    Judge retrieved articles in rank order; stop at the first "fully".
    The best verdict across the first JUDGE_TOP_K is the question's verdict.

    Articles scoring below RETRIEVAL_FLOOR are not sent: classify_failure
    calls those content gaps whatever the judge says, so the call is wasted.
    """
    best = None
    candidates = [a for a in group["retrieved"][:JUDGE_TOP_K] if a["score"] >= RETRIEVAL_FLOOR]
    if group["retrieved"] and not candidates:
        return {"verdict": "not", "reason": "No retrieved article scored above the retrieval floor.",
                "missing": None, "article_id": None}
    for article in candidates:
        verdict = judge_coverage(group["canonical"], article, names=names)
        verdict["verdict"] = str(verdict.get("verdict", "error")).strip().lower()
        if verdict["verdict"] not in _VERDICT_RANK:
            verdict["verdict"] = "error"
        verdict["article_id"] = article["article_id"]
        if best is None or _VERDICT_RANK[verdict["verdict"]] < _VERDICT_RANK[best["verdict"]]:
            best = verdict
        if best["verdict"] == "fully":
            break
    return best or {"verdict": "not", "reason": "No article was retrieved.", "missing": None}


def _route_one(group: dict, routed: list, flows: dict, names) -> dict | None:
    flows_seen = [str(r).strip() for r in routed if pd.notna(r) and str(r).strip()]
    if not flows_seen:
        return None
    flow = Counter(flows_seen).most_common(1)[0][0]
    info = flows.get(flow.lower(), {"name": flow, "description": "(not in the bot-flow file)"})
    result = judge_routing(group["canonical"], info["name"], info["description"], names=names)
    return {"flow": info["name"], "verdict": result.get("verdict", "error"),
            "reason": result.get("reason")}


def judge_all(groups, flows, routed_intent, names=None, concurrency=JUDGE_CONCURRENCY,
              on_progress=None) -> None:
    """Judge every group concurrently. One LLM call per question-article pair."""

    def work(g):
        g["judgement"] = _judge_one(g, names)
        g["routing"] = (
            _route_one(g, [routed_intent[r] for r in g["rows"]], flows, names)
            if routed_intent is not None else None
        )
        return g

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(work, g) for g in groups]
        for f in as_completed(futures):
            f.result()
            done += 1
            if on_progress:
                on_progress(done, len(groups))


# ─────────────────────────────────────────────────────────────
# STEP — CLASSIFY + SHAPE
# ─────────────────────────────────────────────────────────────

def _outcome_bucket(value) -> str | None:
    v = str(value).lower()
    if re.search(r"self|resolv|contain|deflect", v):
        return "selfServed"
    if re.search(r"abandon|drop|timeout|timed out", v):
        return "abandoned"
    if re.search(r"escalat|agent|transfer|handoff|live", v):
        return "escalated"
    return None


def outcomes_for(rows, escalated, outcome) -> dict:
    """
    Per-question outcome counts. Without an outcome column only escalation
    is known; self-served and abandoned stay None rather than being guessed.
    """
    if outcome is not None:
        counts = Counter(_outcome_bucket(outcome[r]) for r in rows)
        return {k: counts.get(k, 0) for k in ("selfServed", "abandoned", "escalated")}
    return {"selfServed": None, "abandoned": None,
            "escalated": int(sum(escalated[r] for r in rows))}


def classify_all(groups, missed_by_retrieval: set[str] | None) -> None:
    for g in groups:
        verdict = g["judgement"]["verdict"]
        kind = classify_failure(g["retrieved"], verdict)
        # A labelled question whose known-relevant article never reached the
        # top K is a retrieval gap, whatever the judge made of the wrong articles.
        if missed_by_retrieval and kind != "covered" and any(
            normalise_question(v) in missed_by_retrieval for v in g["variants"]
        ):
            kind = "retrieval_gap"
        g["failureType"] = kind


def to_records(groups, escalated, outcome) -> list[dict]:
    records = []
    for i, g in enumerate(groups, start=1):
        j = g["judgement"]
        missing = j.get("missing")
        records.append({
            "id": f"q-{i:03d}",
            "canonical": g["canonical"],
            "frequency": g["frequency"],
            "variants": g["variants"],
            "failureType": g["failureType"],
            "verdict": j["verdict"],
            "reason": j.get("reason"),
            "requiredContent": missing if missing not in (None, "", "null") else None,
            "judgedArticleId": j.get("article_id"),
            "retrieved": [
                {"articleId": r["article_id"], "title": r["title"], "score": round(r["score"], 4)}
                for r in g["retrieved"]
            ],
            "routing": g.get("routing"),
            "outcomes": outcomes_for(g["rows"], escalated, outcome),
        })
    return records


def save_outputs(records: list[dict], out_dir: str) -> None:
    with open(os.path.join(out_dir, "question_evaluation.json"), "w") as f:
        json.dump(records, f, indent=2, default=str)
    flat = pd.DataFrame([{
        **{k: v for k, v in r.items() if k not in ("variants", "retrieved", "routing", "outcomes")},
        "variants": " | ".join(r["variants"]),
        "top_article": r["retrieved"][0]["title"] if r["retrieved"] else "",
        "top_score": r["retrieved"][0]["score"] if r["retrieved"] else None,
        "routed_flow": (r["routing"] or {}).get("flow"),
        "routing_verdict": (r["routing"] or {}).get("verdict"),
        **{f"outcome_{k}": v for k, v in r["outcomes"].items()},
    } for r in records])
    flat.to_csv(os.path.join(out_dir, "question_evaluation.csv"), index=False)


# ─────────────────────────────────────────────────────────────
# FULL STAGE
# ─────────────────────────────────────────────────────────────

def run_evaluation(questions: pd.DataFrame, embeddings: np.ndarray, kb_file: str,
                   flow_file: str, out_dir: str, names=None, labelled_file: str | None = None,
                   embedder=None, on_step=None, on_judge_progress=None) -> dict:
    """
    questions: one row per asked question, with `utterance` (original
    text), `clean_text` (what was embedded), `escalated`, and optionally
    `outcome` and `routed_intent`. embeddings align with its rows.

    on_step(key, status) reports dedupe / index / retrieve / judge.
    """
    step = on_step or (lambda key, status: None)
    questions = questions.reset_index(drop=True)

    step("dedupe", "running")
    groups = group_questions(questions["utterance"].astype(str).tolist(),
                             questions["clean_text"].astype(str).tolist(), embeddings)
    print(f"🧩  {len(questions):,} questions → {len(groups):,} distinct")
    step("dedupe", "completed")

    step("index", "running")
    index = get_index(kb_file, embedder=embedder)
    flows = load_flows(flow_file)
    missed = None
    if labelled_file and os.path.exists(labelled_file):
        missed = retrieval_gaps(index, load_labelled_set(labelled_file))
        print(f"🏷️  Labelled set: {len(missed)} questions miss their article in the top {TOP_K}")
    step("index", "completed")

    step("retrieve", "running")
    retrieve_all(groups, index)
    step("retrieve", "completed")

    step("judge", "running")
    routed = questions["routed_intent"].tolist() if "routed_intent" in questions.columns else None
    judge_all(groups, flows, routed, names=names, on_progress=on_judge_progress)
    classify_all(groups, missed)
    step("judge", "completed")

    escalated = questions["escalated"].fillna(0).astype(float).tolist()
    outcome = questions["outcome"].tolist() if "outcome" in questions.columns else None
    records = to_records(groups, escalated, outcome)
    save_outputs(records, out_dir)
    return {"questions": records, "retrievalMeasured": missed is not None}


def run(questions_file: str, kb_file: str, flow_file: str, out_dir: str):
    import improved_utterance_analysis as s1

    os.makedirs(out_dir, exist_ok=True)
    cfg = {**s1.CFG, "INPUT_FILE": questions_file, "OUTPUT_DIR": out_dir}
    df = s1.load_data(cfg)
    embeddings = s1.embed(df, cfg)
    result = run_evaluation(df, embeddings, kb_file, flow_file, out_dir,
                            labelled_file=os.environ.get("LABELLED_SET_FILE"))

    print("\n" + "═" * 70)
    print("TOP QUESTIONS  —  ranked by frequency")
    print("═" * 70)
    for q in result["questions"][:20]:
        print(f"  {q['frequency']:>5}  {q['failureType']:<14} {q['canonical'][:60]}")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    run(*sys.argv[1:5])
