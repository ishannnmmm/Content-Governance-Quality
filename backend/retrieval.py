"""Hybrid retrieval over whole KB articles. No chunking — articles are under
500 words, so splitting them separates questions from answers."""
import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder

from eval_config import (
    CANDIDATES, EMBED_MODEL, KB_ID_COL, KB_TEXT_COL, KB_TITLE_COL,
    RERANK_MODEL, RRF_K, TOP_K,
)


def load_kb(path: str) -> pd.DataFrame:
    """
    Read the KB and map its headers onto article_id / title / content.

    Fails loudly on a missing column. A silent mismatch here is what made
    every question look "not covered" in the old pipeline.
    """
    kb = pd.read_csv(path, encoding="utf-8-sig")
    kb.columns = kb.columns.str.strip()
    lower = {c.lower(): c for c in kb.columns}

    mapping = {}
    for wanted, configured in (("article_id", KB_ID_COL), ("title", KB_TITLE_COL),
                               ("content", KB_TEXT_COL)):
        actual = configured if configured in kb.columns else lower.get(configured.lower())
        if actual is None:
            raise ValueError(
                f"KB file has no '{configured}' column (needed as {wanted}). "
                f"Found: {', '.join(kb.columns)}. Set {wanted.upper()} mapping via "
                f"KB_ID_COL / KB_TITLE_COL / KB_TEXT_COL."
            )
        mapping[actual] = wanted

    kb = kb.rename(columns=mapping)[["article_id", "title", "content"]]
    kb["article_id"] = kb["article_id"].astype(str)
    kb["title"] = kb["title"].fillna("").astype(str)
    kb["content"] = kb["content"].fillna("").astype(str)
    return kb


class KBIndex:
    def __init__(self, kb: pd.DataFrame, embedder: SentenceTransformer | None = None):
        self.kb = kb.reset_index(drop=True)
        # Title prepended: it carries disambiguating signal the body omits.
        self.texts = (
            self.kb["title"].fillna("") + "\n\n" + self.kb["content"].fillna("")
        ).tolist()

        self.embedder = embedder or SentenceTransformer(EMBED_MODEL)
        self.embeddings = self.embedder.encode(
            self.texts, normalize_embeddings=True, show_progress_bar=True
        )
        self.bm25 = BM25Okapi([t.lower().split() for t in self.texts])
        self.reranker = CrossEncoder(RERANK_MODEL)

    def search(self, query: str, k: int = TOP_K, candidates: int = CANDIDATES):
        dense = self._dense(query, candidates)
        sparse = self._sparse(query, candidates)
        fused = self._rrf(dense, sparse)[:candidates]
        return self._rerank(query, fused, k)

    def _dense(self, query, n):
        q = self.embedder.encode(query, normalize_embeddings=True)
        scores = self.embeddings @ q
        return np.argsort(-scores)[:n].tolist()

    def _sparse(self, query, n):
        scores = self.bm25.get_scores(query.lower().split())
        return np.argsort(-scores)[:n].tolist()

    @staticmethod
    def _rrf(*rankings, k: int = RRF_K):
        """Reciprocal rank fusion — combines lists without tuning weights."""
        scores: dict[int, float] = {}
        for ranking in rankings:
            for rank, idx in enumerate(ranking):
                scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
        return sorted(scores, key=scores.get, reverse=True)

    def _rerank(self, query, indices, k):
        if not indices:
            return []
        pairs = [(query, self.texts[i]) for i in indices]
        scores = self.reranker.predict(pairs)
        order = np.argsort(-scores)[:k]
        return [
            {
                "article_id": self.kb.iloc[indices[i]]["article_id"],
                "title": self.kb.iloc[indices[i]]["title"],
                "content": self.kb.iloc[indices[i]]["content"],
                "score": float(scores[i]),
            }
            for i in order
        ]
