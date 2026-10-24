"""Group near-identical questions so each distinct question appears once."""
import numpy as np
from sklearn.cluster import AgglomerativeClustering

from eval_config import DEDUPE_THRESHOLD


def canonicalise(questions, embeddings, threshold=DEDUPE_THRESHOLD):
    """Agglomerative clustering with a distance cutoff — unlike k-means,
    this needs no k and groups only genuinely similar phrasings.

    Each group also carries `indices` (positions in `questions`) so callers
    can join back to per-row data such as outcomes and routed intent.
    """
    if len(questions) < 2:
        return [{"canonical": q, "variants": [q], "frequency": 1, "indices": [i]}
                for i, q in enumerate(questions)]

    labels = AgglomerativeClustering(
        n_clusters=None, distance_threshold=threshold,
        metric="cosine", linkage="average",
    ).fit_predict(embeddings)

    groups = []
    for label in set(labels):
        idx = np.where(labels == label)[0]
        variants = [questions[i] for i in idx]
        # The variant closest to the group centre is the clearest phrasing.
        centroid = embeddings[idx].mean(axis=0)
        best = idx[np.argmax(embeddings[idx] @ centroid)]
        groups.append({
            "canonical": questions[best],
            "variants": variants,
            "frequency": len(variants),
            "indices": idx.tolist(),
        })

    return sorted(groups, key=lambda g: g["frequency"], reverse=True)
