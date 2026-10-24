"""
improved_utterance_analysis.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage 1 — Utterance Intelligence (improved metro_boomin.py)

Loads extracted questions and embeds them (with an .npy cache). In the
KB evaluation pipeline that is all it is used for: the unit of analysis
is the canonical question (canonical.py), not a cluster.

K-means grouping and LLM topic naming remain as an optional navigation
aid. pick_best_k / silhouette, frustration_index and priority_score are
retired — nothing depends on an optimal k, and question frequency plus
failure type replace the scores.
"""

import os
import json
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from llm_client import ask

# ─────────────────────────────────────────────────────────────
# CONFIGURATION  — edit these paths before running
# ─────────────────────────────────────────────────────────────
CFG = dict(
    INPUT_FILE   = "Book44.csv",          # raw utterances CSV
    UTT_COL      = "utterance",
    ESC_COL      = "chatOfferAccepted",

    MODEL_NAME   = "all-MiniLM-L6-v2",

    # Fixed number of navigation topics (optional grouping only)
    N_TOPICS     = 8,

    OUTPUT_DIR   = "analysis_outputs",
)

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)


def load_data(cfg):
    print("📂  Loading utterances...")
    try:
        df = pd.read_csv(cfg["INPUT_FILE"], encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(cfg["INPUT_FILE"], encoding="latin1")
    df.columns = df.columns.str.strip()

    # Normalise escalation flag
    esc = cfg["ESC_COL"]
    if esc in df.columns:
        df["escalated"] = (
            df[esc].astype(str).str.upper().str.strip()
                   # "1.0"/"0.0": the flag comes back as float after a pandas round trip
                   .map({"TRUE": 1, "FALSE": 0, "1": 1, "0": 0, "1.0": 1, "0.0": 0})
                   .fillna(0).astype(float)
        )
    else:
        print(f"  ⚠️  Column '{esc}' not found — escalation set to 0")
        df["escalated"] = 0.0

    df["clean_text"] = df[cfg["UTT_COL"]].fillna("").astype(str).str.lower().str.strip()
    print(f"  Loaded {len(df):,} utterances")
    return df


# ─────────────────────────────────────────────────────────────
# STEP 1 — SENTIMENT  (VADER with intensity buckets)
# ─────────────────────────────────────────────────────────────

def add_sentiment(df):
    print("📊  Running sentiment analysis...")
    analyzer = SentimentIntensityAnalyzer()
    scores = df["clean_text"].apply(lambda x: analyzer.polarity_scores(x)["compound"])
    df["sentiment_score"] = scores

    # Human-readable bucket
    def bucket(s):
        if s >=  0.35: return "Positive"
        if s <= -0.35: return "Negative"
        return "Neutral"

    df["sentiment_label"] = df["sentiment_score"].apply(bucket)
    dist = df["sentiment_label"].value_counts().to_dict()
    print(f"  Sentiment distribution: {dist}")
    return df


# ─────────────────────────────────────────────────────────────
# STEP 2 — EMBED
# ─────────────────────────────────────────────────────────────

def embed(df, cfg):
    print(f"🔢  Encoding with {cfg['MODEL_NAME']}...")
    model = SentenceTransformer(cfg["MODEL_NAME"])
    embeddings = model.encode(
        df["clean_text"].tolist(),
        show_progress_bar=True,
        batch_size=64,
        normalize_embeddings=True,
    )
    # Save to disk — Stage 2 will load this instead of re-encoding
    emb_path = os.path.join(cfg["OUTPUT_DIR"], "utterance_embeddings.npy")
    np.save(emb_path, embeddings)
    print(f"  Embeddings saved → {emb_path}")
    return embeddings


# ─────────────────────────────────────────────────────────────
# STEP 3 — OPTIONAL TOPIC GROUPING
# ─────────────────────────────────────────────────────────────
# Demoted: the unit of analysis is now the canonical question (see
# canonical.py). K-means remains only as a coarse navigation grouping,
# with a fixed k — nothing depends on an "optimal" k any more.

def cluster(df, embeddings, k):
    print(f"🤖  Grouping into {k} navigation topics...")
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    df["cluster"] = km.fit_predict(embeddings)
    return df


# ─────────────────────────────────────────────────────────────
# STEP 4 — LLM TOPIC NAMING  (via llm_client — scrubbed)
# ─────────────────────────────────────────────────────────────

def name_clusters_with_llm(df, cfg, names=None):
    """
    For each group, send 20 sample utterances to the LLM and get back
    a short, human-readable topic label + one-line description.
    Falls back to a generic name if the API key is missing.

    Goes through llm_client.ask(), which scrubs PII — pass the speaker
    names as `names` so bare first names are caught too.
    """
    if not os.environ.get("GROQ_API_KEY", ""):
        print("  ⚠️  GROQ_API_KEY not set — using generic cluster names")
        return {cid: f"Cluster {cid}" for cid in df["cluster"].unique()}

    print("🧠  Naming topics with the LLM...")
    cluster_names = {}

    for cid in sorted(df["cluster"].unique()):
        samples = (
            df[df["cluster"] == cid]["clean_text"]
            .dropna()
            .sample(min(20, len(df[df["cluster"] == cid])), random_state=42)
            .tolist()
        )
        samples_str = "\n".join(f"- {s}" for s in samples)

        prompt = f"""You are analyzing customer support utterances grouped into clusters.
Here are sample utterances from cluster {cid}:

{samples_str}

Respond ONLY with a JSON object with two keys:
- "label": a 2-4 word topic name (e.g. "Claim Status Inquiry")
- "description": one sentence describing the customer need

No preamble, no markdown, just the JSON."""

        try:
            raw = ask(prompt, max_tokens=150, names=names).strip()
            parsed = json.loads(raw)
            label = parsed.get("label", f"Cluster {cid}")
            desc  = parsed.get("description", "")
            cluster_names[cid] = label
            print(f"  Cluster {cid:2d} → {label}")
            if desc:
                print(f"             {desc}")
        except Exception as e:
            print(f"  ⚠️  Cluster {cid} naming failed: {e}")
            cluster_names[cid] = f"Cluster {cid}"

    return cluster_names


# ─────────────────────────────────────────────────────────────
# STEP 6 — SUMMARY TABLE
# ─────────────────────────────────────────────────────────────

def build_summary(df, cluster_names):
    print("📋  Building cluster summary...")
    summary = (
        df.groupby("cluster")
          .agg(
              volume          = ("clean_text", "count"),
              escalation_rate = ("escalated", "mean"),
              avg_sentiment   = ("sentiment_score", "mean"),
          )
          .reset_index()
    )

    summary["cluster_name"] = summary["cluster"].map(cluster_names)
    summary = summary.sort_values("volume", ascending=False).reset_index(drop=True)
    summary["rank"] = summary.index + 1
    return summary


# ─────────────────────────────────────────────────────────────
# STEP 6 — SAVE
# ─────────────────────────────────────────────────────────────

def save_outputs(df, summary, cfg):
    out = cfg["OUTPUT_DIR"]

    # Detailed utterance CSV
    utt_path = os.path.join(out, "utterances_clustered.csv")
    df[["clean_text", "escalated", "sentiment_score", "sentiment_label", "cluster"]].to_csv(utt_path, index=False)
    print(f"\n✅  Utterance CSV → {utt_path}")

    # Summary CSV
    sum_path = os.path.join(out, "cluster_summary.csv")
    summary.to_csv(sum_path, index=False)
    print(f"✅  Cluster summary → {sum_path}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def run(cfg=CFG):
    ensure_dir(cfg["OUTPUT_DIR"])
    df                      = load_data(cfg)
    df                      = add_sentiment(df)
    embeddings              = embed(df, cfg)
    df                      = cluster(df, embeddings, cfg["N_TOPICS"])
    cluster_names           = name_clusters_with_llm(df, cfg)
    summary                 = build_summary(df, cluster_names)
    save_outputs(df, summary, cfg)

    print("\n" + "═" * 60)
    print("TOPIC TABLE  (navigation grouping, by volume)")
    print("═" * 60)
    cols = ["rank", "cluster_name", "volume", "escalation_rate", "avg_sentiment"]
    print(summary[cols].to_string(index=False))
    print("═" * 60)
    return df, summary


if __name__ == "__main__":
    run()