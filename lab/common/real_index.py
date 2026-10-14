"""Hybrid retrieval with a real pretrained dense leg, in place of TF-IDF.

A real-model counterpart to lab/common/index.py. The sparse leg (Okapi BM25) is
unchanged and reused as-is. The dense leg uses the real pretrained spaCy word
vectors from lab/common/real_models.py instead of sklearn TfidfVectorizer cosine.
"""

from __future__ import annotations

import numpy as np

from lab.common.index import BM25, tokenize
from lab.common.real_models import real_vector


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _filters_ok(passage: dict, filters: dict) -> bool:
    for key, value in filters.items():
        if value is None:
            continue
        current = passage.get(key)
        if isinstance(value, (list, tuple, set)):
            if current not in value:
                return False
        elif current != value:
            return False
    return True


class RealIndex:
    def __init__(self, passages: list[dict]):
        self.passages = list(passages)
        self._tokens = [tokenize(p.get("text", "")) for p in self.passages]
        self.bm25 = BM25(self._tokens)
        vectors = np.stack(
            [real_vector(p.get("text", "") or "") for p in self.passages]
        ) if self.passages else np.zeros((0, 300), dtype="float32")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.unit_vectors = vectors / norms

    def _dense(self, query: str) -> list[float]:
        if not self.passages:
            return []
        qv = real_vector(query)
        qn = float(np.linalg.norm(qv))
        if qn == 0.0:
            return [0.0] * len(self.passages)
        unit_q = qv / qn
        return [float(v) for v in (self.unit_vectors @ unit_q)]

    def search(
        self,
        query: str,
        top_k: int = 10,
        exclude: set[str] | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        exclude = exclude or set()
        filters = filters or {}
        q_tokens = tokenize(query)
        dense = self._dense(query)
        sparse = [self.bm25.score(q_tokens, i) for i in range(len(self.passages))]
        dense_n = _minmax(dense)
        sparse_n = _minmax(sparse)
        ranked = []
        for i, passage in enumerate(self.passages):
            if passage.get("id") in exclude:
                continue
            if not _filters_ok(passage, filters):
                continue
            hybrid = 0.5 * dense_n[i] + 0.5 * sparse_n[i]
            ranked.append(
                {"passage": passage, "score": hybrid, "dense": dense[i], "sparse": sparse[i]}
            )
        ranked.sort(key=lambda row: row["score"], reverse=True)
        return ranked[:top_k]
