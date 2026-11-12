"""In-memory hybrid retrieval: BM25 + TF-IDF, plus a lexical reranker.

EXP-022 adds Index.save/load: BM25 has no real "fit" step beyond
counting (cheap to rebuild from the saved token lists), but the fitted
TfidfVectorizer and its sparse document matrix are genuinely expensive
to recompute over a large corpus -- those are persisted via pickle so a
later process can load and search without re-fitting over the full
corpus again, the actual need EXP-022 names ("once the corpus no longer
fits the process index"). Still an in-process index once loaded (no
Qdrant/on-disk ANN structure); this persists the FITTED STATE, not a
disk-backed query engine -- a real distinction, named honestly in
EXP-022's own scale_down, not papered over.
"""

from __future__ import annotations

import math
import pickle
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from lab.common.textutil import content_tokens, jaccard, tokens

_TOKEN = re.compile(r"[a-z0-9]+", re.I)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = docs
        self.n = len(docs)
        self.df: dict[str, int] = {}
        self.tf: list[dict[str, int]] = []
        self.lengths = []
        for doc in docs:
            counts: dict[str, int] = {}
            for term in doc:
                counts[term] = counts.get(term, 0) + 1
            self.tf.append(counts)
            self.lengths.append(len(doc))
            for term in counts:
                self.df[term] = self.df.get(term, 0) + 1
        self.avgdl = (sum(self.lengths) / self.n) if self.n else 0.0

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def score(self, query: list[str], idx: int) -> float:
        if self.n == 0 or self.avgdl == 0:
            return 0.0
        tf = self.tf[idx]
        dl = self.lengths[idx] or 1
        total = 0.0
        for term in query:
            freq = tf.get(term, 0)
            if not freq:
                continue
            idf = self.idf(term)
            denom = freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            total += idf * (freq * (self.k1 + 1)) / denom
        return total


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


class Index:
    def __init__(self, passages: list[dict]):
        self.passages = list(passages)
        self._tokens = [tokenize(p.get("text", "")) for p in self.passages]
        self.bm25 = BM25(self._tokens)
        corpus = [p.get("text", "") or "" for p in self.passages]
        if any(corpus):
            self.vectorizer = TfidfVectorizer(stop_words="english")
            self.matrix = self.vectorizer.fit_transform(corpus)
        else:
            self.vectorizer = None
            self.matrix = None

    def _dense(self, query: str) -> list[float]:
        if self.vectorizer is None or self.matrix is None:
            return [0.0] * len(self.passages)
        qv = self.vectorizer.transform([query])
        sims = cosine_similarity(qv, self.matrix).ravel()
        return [float(s) for s in sims]

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
                {
                    "passage": passage,
                    "score": hybrid,
                    "dense": dense[i],
                    "sparse": sparse[i],
                }
            )
        ranked.sort(key=lambda row: row["score"], reverse=True)
        return ranked[:top_k]

    def save(self, path: str | Path) -> None:
        """Persists the fitted vectorizer+matrix and BM25's own input
        token lists (from which BM25's df/tf/lengths/avgdl rebuild
        deterministically and cheaply -- no need to persist those
        derived values separately). Passages are persisted too, so
        `load` returns a fully usable Index with no reference back to
        whatever built the original.
        """
        with open(path, "wb") as f:
            pickle.dump({"passages": self.passages, "tokens": self._tokens, "vectorizer": self.vectorizer, "matrix": self.matrix}, f)

    @classmethod
    def load(cls, path: str | Path) -> "Index":
        with open(path, "rb") as f:
            state = pickle.load(f)
        index = cls.__new__(cls)
        index.passages = state["passages"]
        index._tokens = state["tokens"]
        index.bm25 = BM25(index._tokens)
        index.vectorizer = state["vectorizer"]
        index.matrix = state["matrix"]
        return index

    def rerank(self, query: str, candidates: list[dict], keep: int = 5) -> list[dict]:
        q_content = content_tokens(query)
        q_toks = tokens(query)
        bigrams = set(zip(q_toks, q_toks[1:]))
        rescored = []
        for row in candidates:
            text = row["passage"].get("text", "")
            p_content = content_tokens(text)
            p_toks = tokens(text)
            cov = 0.0
            if q_content:
                cov = sum(1 for t in set(q_content) if t in set(p_content)) / len(set(q_content))
            jac = jaccard(q_content, p_content)
            p_bigrams = set(zip(p_toks, p_toks[1:]))
            phrase = 1.0 if bigrams and (bigrams & p_bigrams) else 0.0
            cross = 0.6 * cov + 0.25 * jac + 0.15 * phrase
            rescored.append({**row, "rerank_score": cross, "score": cross})
        rescored.sort(key=lambda row: row["rerank_score"], reverse=True)
        return rescored[:keep]


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
