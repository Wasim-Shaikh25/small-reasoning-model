"""Semantic (bge embedding) retrieval and navigation, as a side-by-side
alternative to lab.common.index.Index's TF-IDF scoring -- kept as its own
module rather than bolted onto Index or lab.common.nested_index, so the two
can be measured against each other (EXP-067) before any decision to wire
one into lab.common.brain in production.

Why margin-based abstention, not a floor (lab.common.nested_index's
approach): that floor works only because disjoint TF-IDF vectors dot-product
to exactly 0.0. Real embeddings don't have that property -- two unrelated
sentences still typically score ~0.1-0.3 cosine similarity, never near
zero -- so a near-zero floor would simply never fire and every ask would get
a confident answer regardless of whether anything actually matched. What
does generalize across both scoring methods: a genuine match should
decisively outscore every other candidate at that level (a large gap between
the best and the runner-up); an ask with no real match has no reason to
prefer any one candidate over the others (a small gap), because nothing in
the tree actually relates to it any more than anything else does.
"""

from __future__ import annotations

import numpy as np

from lab.common.index import Index
from lab.common.nested_index import MIN_DENSE_SCORE
from lab.common.real_encoders import bge_embed

# First measured value (EXP-067): separated a genuine paraphrase match
# (margin 0.0403) from an off-topic non-match (margin 0.0146) on one fixture.
# That gap is narrow enough that this is a starting point, not a validated
# constant -- see EXP-068's sweep across multiple fixtures before trusting it
# further than this.
MIN_SEMANTIC_MARGIN = 0.03


class SemanticIndex:
    def __init__(self, passages: list[dict]):
        self.passages = list(passages)
        texts = [p.get("text", "") or "" for p in self.passages]
        self.vectors = bge_embed(texts) if texts else np.zeros((0, 1), dtype="float32")

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        if not self.passages:
            return []
        qv = bge_embed([query])[0]
        sims = self.vectors @ qv
        ranked = sorted(
            ({"passage": p, "score": float(s)} for p, s in zip(self.passages, sims)),
            key=lambda row: row["score"],
            reverse=True,
        )
        return ranked[:top_k]


def navigate_semantic(ask: str, root, min_margin: float = MIN_SEMANTIC_MARGIN) -> dict:
    """Same shape and descent logic as lab.common.nested_index.navigate, but
    scored by bge cosine similarity and abstaining on a small top1-vs-runner-up
    margin instead of an absolute floor.

    Margin needs at least 2 children to mean anything; with exactly 1 child
    there is no runner-up to compare against, so a margin can't be computed
    at all. Rather than proceeding unconditionally (the original gap), this
    falls back to the one check that doesn't need a second candidate: the
    same TF-IDF dense-score floor lab.common.nested_index uses (MIN_DENSE_SCORE),
    scored on this single child against the ask. That floor's own logic
    (disjoint vocabulary dot-products to exactly 0.0) holds regardless of how
    many candidates there are, which is exactly why it can plug the gap the
    margin check leaves open here -- it just can't catch a paraphrase the way
    the margin check can, which is why it's the fallback and not the primary
    mechanism when a real choice exists.
    """
    trace = []
    node = root
    while not node.is_leaf:
        candidates = [{"id": child.node_id, "text": child.summary_text} for child in node.children]
        child_level = node.children[0].level

        if len(candidates) == 1:
            dense = Index(candidates).search(ask, top_k=1)[0]["dense"]
            if dense < MIN_DENSE_SCORE:
                return {
                    "path": trace,
                    "leaf": None,
                    "leaf_passages": [],
                    "abstain_reason": (
                        f"only one {child_level} candidate and it scored at the dense-similarity floor "
                        f"(dense {dense:.4f} < {MIN_DENSE_SCORE}) -- no margin was computable to check instead"
                    ),
                }
            chosen = node.children[0]
            trace.append({"level": chosen.level, "chosen": chosen.title, "chosen_id": chosen.node_id, "score": None, "margin": None, "candidates_considered": 1, "fallback": "single_candidate_dense_floor"})
            node = chosen
            continue

        index = SemanticIndex(candidates)
        hits = index.search(ask, top_k=2)
        if not hits:
            return {"path": trace, "leaf": None, "leaf_passages": [], "abstain_reason": f"no {child_level} candidates to score"}
        margin = hits[0]["score"] - hits[1]["score"]
        if margin < min_margin:
            return {
                "path": trace,
                "leaf": None,
                "leaf_passages": [],
                "abstain_reason": (
                    f"no {child_level} clearly separated from the runner-up "
                    f"(margin {margin:.4f} < {min_margin}, top score {hits[0]['score']:.4f})"
                ),
            }
        best_id = hits[0]["passage"]["id"]
        chosen = next(child for child in node.children if child.node_id == best_id)
        trace.append(
            {
                "level": chosen.level,
                "chosen": chosen.title,
                "chosen_id": chosen.node_id,
                "score": round(hits[0]["score"], 4),
                "margin": round(margin, 4),
                "candidates_considered": len(candidates),
            }
        )
        node = chosen
    return {"path": trace, "leaf": node, "leaf_passages": node.leaf_passages}
