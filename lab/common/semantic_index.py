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

from lab.common.real_encoders import bge_embed


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


def navigate_semantic(ask: str, root, min_margin: float = 0.03) -> dict:
    """Same shape and descent logic as lab.common.nested_index.navigate, but
    scored by bge cosine similarity and abstaining on a small top1-vs-runner-up
    margin instead of an absolute floor. Needs at least 2 children at a level
    to compute a margin; with exactly 1 child there is no ambiguity to resolve
    (nothing to disambiguate against), so it proceeds unconditionally -- a
    known gap if a single-child level is itself the wrong branch, not
    exercised by this module's fixtures.
    """
    trace = []
    node = root
    while not node.is_leaf:
        candidates = [{"id": child.node_id, "text": child.summary_text} for child in node.children]
        child_level = node.children[0].level
        index = SemanticIndex(candidates)
        hits = index.search(ask, top_k=2)
        if not hits:
            return {"path": trace, "leaf": None, "leaf_passages": [], "abstain_reason": f"no {child_level} candidates to score"}
        margin = hits[0]["score"] - hits[1]["score"] if len(hits) > 1 else hits[0]["score"]
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
