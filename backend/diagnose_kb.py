"""Sanity-check the KB and bot-flow files before building anything on them."""
import sys

import pandas as pd
from sentence_transformers import SentenceTransformer, util

KB_FILE = sys.argv[1] if len(sys.argv) > 1 else "kb_articles.csv"
FLOW_FILE = sys.argv[2] if len(sys.argv) > 2 else "bot_flows_tgr.csv"

kb = pd.read_csv(KB_FILE, encoding="utf-8-sig")
kb.columns = kb.columns.str.strip()
print(f"Columns:  {list(kb.columns)}")
print(f"Articles: {len(kb):,}")

for col in ("article_id", "title", "content"):
    if col not in kb.columns:
        print(f"  MISSING COLUMN: {col}")
        continue
    empty = kb[col].isna().sum() + (kb[col].astype(str).str.strip() == "").sum()
    print(f"  {col:12s} empty: {empty:,}")

if "content" in kb.columns:
    words = kb["content"].fillna("").astype(str).str.split().str.len()
    print(f"  content words — median {words.median():.0f}, "
          f"max {words.max():.0f}, under 20 words: {(words < 20).sum():,}")

print("\nFirst article:")
print(kb.iloc[0].to_dict() if len(kb) else "  EMPTY FILE")

# Does retrieval return anything sane?
model = SentenceTransformer("all-MiniLM-L6-v2")
texts = (kb["title"].fillna("") + "\n\n" + kb["content"].fillna("")).tolist()
emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)

probes = [
    "why was i charged twice this month",
    "how do i update my payment card",
    "when will my claim be processed",
    "i cannot log in to my account",
]
print("\nRetrieval probe:")
for q in probes:
    scores = util.cos_sim(model.encode(q, normalize_embeddings=True), emb)[0]
    top = scores.topk(min(3, len(kb)))
    print(f"\n  {q}")
    for score, idx in zip(top.values, top.indices):
        print(f"    {score:.3f}  {str(kb.iloc[int(idx)]['title'])[:70]}")

flows = pd.read_csv(FLOW_FILE, encoding="utf-8-sig")
flows.columns = flows.columns.str.strip()
print(f"\nFlow columns: {list(flows.columns)}")
print(f"Flows: {len(flows):,}")
