"""
metrics.py
━━━━━━━━━━
Retrieval metrics (Recall@K, MRR), judge-agreement checks, and the
per-run aggregates the frontend shows.

Two gates from the implementation guide live here:
  • Recall@5 above 0.8 before building on the judge
        python metrics.py retrieval kb_articles.csv labelled_questions.csv
  • Judge agreement near human agreement before reporting any number
        python metrics.py agreement labels.csv

labelled_questions.csv: columns `question`, `relevant_article_ids`
(semicolon-separated). Write 50-100 from article titles yourself.

labels.csv: one row per query-article pair, columns `reviewer_a`,
`reviewer_b`, `judge` holding verdicts (fully / partially / not).
"""
import re
import sys

import pandas as pd

from eval_config import TOP_K


def recall_at_k(results, relevant_ids, k=5):
    retrieved = {r["article_id"] for r in results[:k]}
    return len(retrieved & set(relevant_ids)) / max(len(relevant_ids), 1)


def reciprocal_rank(results, relevant_ids):
    for rank, r in enumerate(results, start=1):
        if r["article_id"] in relevant_ids:
            return 1.0 / rank
    return 0.0


def normalise_question(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(text).lower()).strip()


def load_labelled_set(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    for col in ("question", "relevant_article_ids"):
        if col not in df.columns:
            raise ValueError(f"Labelled set needs a '{col}' column. Found: {list(df.columns)}")
    df["relevant"] = df["relevant_article_ids"].fillna("").astype(str).apply(
        lambda s: [x.strip() for x in s.split(";") if x.strip()]
    )
    return df


def evaluate_retrieval(index, labelled: pd.DataFrame, k: int = TOP_K) -> dict:
    """Run every labelled question through the index; return Recall@K and MRR."""
    rows = []
    for _, row in labelled.iterrows():
        results = index.search(row["question"], k=k)
        rows.append({
            "question": row["question"],
            "relevant": row["relevant"],
            "retrieved": [r["article_id"] for r in results],
            "recall": recall_at_k(results, row["relevant"], k),
            "rr": reciprocal_rank(results, row["relevant"]),
        })
    detail = pd.DataFrame(rows)
    return {
        "k": k,
        "n": len(detail),
        "recall_at_k": float(detail["recall"].mean()) if len(detail) else 0.0,
        "mrr": float(detail["rr"].mean()) if len(detail) else 0.0,
        "detail": detail,
    }


def retrieval_gaps(index, labelled: pd.DataFrame, k: int = TOP_K) -> set[str]:
    """
    Normalised labelled questions whose relevant article exists but did not
    appear in the top K. This is the only way to see a retrieval gap — per
    query, a miss is indistinguishable from a content gap.
    """
    evaluated = evaluate_retrieval(index, labelled, k)["detail"]
    missed = evaluated[evaluated["recall"] == 0]
    return {normalise_question(q) for q in missed["question"]}


def agreement(a, b) -> dict:
    """Raw agreement and Cohen's kappa between two label sequences."""
    from sklearn.metrics import cohen_kappa_score

    a, b = list(a), list(b)
    raw = sum(x == y for x, y in zip(a, b)) / max(len(a), 1)
    return {"n": len(a), "agreement": raw, "kappa": float(cohen_kappa_score(a, b))}


def judge_validation(labels: pd.DataFrame) -> dict:
    """
    Human-vs-human first (the ceiling), then judge-vs-consensus on the
    rows where the humans agreed.
    """
    human = agreement(labels["reviewer_a"], labels["reviewer_b"])
    consensus = labels[labels["reviewer_a"] == labels["reviewer_b"]]
    judge = agreement(consensus["reviewer_a"], consensus["judge"])
    verdict_mix = labels["judge"].value_counts(normalize=True).round(3).to_dict()
    return {"human": human, "judge_vs_consensus": judge, "judge_verdict_mix": verdict_mix}


def run_aggregates(questions: list[dict], retrieval_measured: bool) -> dict:
    """The summary block of the frontend payload."""
    total = sum(q["frequency"] for q in questions)
    covered = sum(q["frequency"] for q in questions if q["failureType"] == "covered")
    judged = sum(q["frequency"] for q in questions if q["failureType"] != "unjudged")

    def count(kind):
        return sum(1 for q in questions if q["failureType"] == kind)

    return {
        "totalQuestions": total,
        "distinctQuestions": len(questions),
        # Weighted by how often each question was asked, over judged ones.
        "answerablePercent": round(covered / judged * 100, 1) if judged else 0.0,
        "contentGaps": count("content_gap"),
        # None means "not measured" — there was no labelled set to check against.
        "retrievalGaps": count("retrieval_gap") if retrieval_measured else None,
        "clarityGaps": count("clarity_gap"),
        "unjudged": count("unjudged"),
    }


def _main(argv):
    if len(argv) >= 3 and argv[0] == "retrieval":
        from retrieval import KBIndex, load_kb

        index = KBIndex(load_kb(argv[1]))
        result = evaluate_retrieval(index, load_labelled_set(argv[2]))
        print(f"\nRecall@{result['k']}: {result['recall_at_k']:.3f}   "
              f"MRR: {result['mrr']:.3f}   (n={result['n']})")
        print("Gate: Recall@5 above 0.8 before trusting the judge.\n")
        misses = result["detail"][result["detail"]["recall"] == 0]
        for _, row in misses.iterrows():
            print(f"  MISS  {row['question'][:70]}  → wanted {row['relevant']}, got {row['retrieved']}")
        return

    if len(argv) >= 2 and argv[0] == "agreement":
        labels = pd.read_csv(argv[1], encoding="utf-8-sig")
        result = judge_validation(labels)
        h, j = result["human"], result["judge_vs_consensus"]
        print(f"Human vs human:      agreement {h['agreement']:.3f}  kappa {h['kappa']:.3f}  (n={h['n']})")
        print(f"Judge vs consensus:  agreement {j['agreement']:.3f}  kappa {j['kappa']:.3f}  (n={j['n']})")
        print(f"Judge verdict mix:   {result['judge_verdict_mix']}")
        if "not" not in result["judge_verdict_mix"]:
            print("⚠️  The judge never returned 'not' — it is broken or the set lacks known negatives.")
        return

    print(__doc__)


if __name__ == "__main__":
    _main(sys.argv[1:])
