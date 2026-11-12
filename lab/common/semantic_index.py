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

# MODEL-VERSION GUARD NOTE (2026-11-03 reasoning-layer audit, AUDIT.md):
# MIN_SEMANTIC_MARGIN and SEMANTIC_SINGLE_FLOOR below were both measured
# against whatever checkpoint bge_embed loaded AT THE TIME (currently
# real_encoders.BGE_MODEL_NAME = "BAAI/bge-small-en-v1.5"), with no
# version pin or runtime check anywhere tying the two together. Changing
# BGE_MODEL_NAME silently invalidates both with zero warning -- re-run
# EXP-067/068 (MIN_SEMANTIC_MARGIN) and EXP-070 (SEMANTIC_SINGLE_FLOOR)
# before trusting either after such a change. Same caveat applies to
# MIN_LEXICAL_MARGIN below, even though it scores TF-IDF, not bge --
# it was calibrated against the SAME fixtures these two were, so a model
# change that shifts what "off-topic" looks like semantically could shift
# which lexical margin counts as decisive too.
# First measured value (EXP-067): separated a genuine paraphrase match
# (margin 0.0403) from an off-topic non-match (margin 0.0146) on one fixture.
# That gap is narrow enough that this is a starting point, not a validated
# constant -- see EXP-068's sweep across multiple fixtures before trusting it
# further than this.
MIN_SEMANTIC_MARGIN = 0.03

# Absolute floor used only where no second candidate exists to take a
# margin against (navigate_dual's single-candidate level). Separates a
# genuine match (0.64-0.74 across every sample measured, EXP-070) from an
# off-topic one (0.34, EXP-068) on a small sample -- not swept across
# fixtures the way MIN_SEMANTIC_MARGIN was, so treat it the same way: a
# first measured value, not a validated constant.
SEMANTIC_SINGLE_FLOOR = 0.5

# EXP-071 found a real gap in the "disagree -> always abstain" rule: lexical
# can clear MIN_DENSE_SCORE (technically nonzero) while its top1-vs-top2 gap
# is pure noise -- measured directly on a real failure (governance_agm's
# paraphrase case): dense scores of 0.2673/0.2640/0.2673 across 3 sections,
# a top1-vs-top2 margin of 0.0033, because every section's summary shares
# the same chapter-level filler vocabulary and the ask shares none of the
# needle's own distinguishing words. Lexical wasn't confident about *which*
# section -- it was just nonzero everywhere -- and that spurious "agreement"
# requirement vetoed a semantic signal that was genuinely decisive (margin
# 0.1126). Giving lexical the same margin-based confidence check already
# used for semantic, not just an absolute floor, fixes this: a technically
# positive but indecisive lexical score no longer counts as "lexical is
# confident" in the disagreement check below. First measured value, not
# swept across many fixtures -- same caveat as MIN_SEMANTIC_MARGIN.
MIN_LEXICAL_MARGIN = 0.01


def dense_margin(hits: list[dict]) -> float:
    """The real top1-vs-runner-up gap in *dense* score, not whatever gap
    happens to exist between hits[0] and hits[1] as Index.search ranks them.

    Index.search sorts by the blended hybrid score (dense and sparse
    combined), not by dense alone -- so the hybrid-ranked runner-up is not
    reliably the second-highest *dense* score. Comparing hits[0]["dense"]
    to hits[1]["dense"] directly can come out negative (EXP-071 found this
    exact bug: the hybrid-top candidate's own dense score was lower than
    the hybrid-runner-up's), which would make MIN_LEXICAL_MARGIN's check
    always fail regardless of whether dense itself was actually decisive.
    `hits` must already include every real candidate (call search with
    top_k=len(candidates), not top_k=2) for this to re-rank correctly.
    """
    dense_sorted = sorted((h["dense"] for h in hits), reverse=True)
    if len(dense_sorted) < 2:
        return dense_sorted[0] if dense_sorted else 0.0
    return dense_sorted[0] - dense_sorted[1]


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


# navigate_semantic (semantic-only descent) moved to lab.tests.support on
# 2026-11-12 -- lab.common.brain's hierarchical_navigate stage calls
# navigate_dual (below) only. navigate_semantic stays reachable from
# lab.tests.support for EXP-067/068's own comparison against navigate_dual.


def navigate_dual(ask: str, root, min_dense_score: float = MIN_DENSE_SCORE, min_margin: float = MIN_SEMANTIC_MARGIN) -> dict:
    """Hierarchical navigation using lexical and semantic as two independent
    signals that must agree, instead of either one alone.

    Until this function existed, lab.common.brain's hierarchical branch used
    the lexical-only navigate function (originally lab.common.nested_index.
    navigate, moved to lab.tests.support on 2026-11-12 once navigate_dual
    superseded it here) -- lexical (TF-IDF) only, so it could
    navigate exact-wording asks but had no way to catch a paraphrased one
    (the same gap EXP-067 measured and fixed for flat disambiguation, never
    carried over to the hierarchical path). navigate_semantic (above) then
    added the opposite gap: semantic (bge) only, and EXP-068's margin sweep
    found its margin alone isn't reliably separable from noise across
    fixtures. This combines both the way lab.common.brain's flat branch
    already does (EXP-067/069): lexical abstains via the near-zero dense
    floor (disjoint TF-IDF vectors are exactly 0.0, regardless of scale);
    semantic abstains via the top1-vs-runner-up margin (catches paraphrase,
    where lexical can't); if only one signal is confident its pick is used,
    if both are confident but disagree that's a real conflict and the level
    abstains rather than guessing, and if both abstain there's nothing to
    recover. A single-candidate level has no margin to compute at all, so it
    checks both the lexical dense floor and an absolute semantic floor
    (SEMANTIC_SINGLE_FLOOR) and proceeds if either clears -- not the dense
    floor alone the way navigate_semantic's single-child fallback does;
    lexical-only there let a correctly-resolved parent level get vetoed one
    level down by a check with no semantic signal (EXP-070).
    """
    trace = []
    node = root
    while not node.is_leaf:
        candidates = [{"id": child.node_id, "text": child.summary_text} for child in node.children]
        child_level = node.children[0].level

        if len(candidates) == 1:
            # No margin is computable with one candidate, so this can't use
            # the same two checks as the multi-candidate branch below. Using
            # the lexical floor alone (the original design) meant a parent
            # level could resolve a heavy paraphrase correctly via the
            # semantic signal, only for that correct answer to be vetoed one
            # level down by a check with no semantic signal at all --
            # measured directly in EXP-070 (chapter correctly resolved via a
            # 0.094 semantic margin, then the single-section level beneath
            # it rejected the same ask because its lexical dense score was
            # exactly 0.0). SEMANTIC_SINGLE_FLOOR is a rough absolute
            # semantic floor, not a margin -- separates a genuine match
            # (0.64-0.74 in every sample measured so far) from an off-topic
            # one (0.34) on a small sample, same unvalidated-beyond-this-
            # sample caveat MIN_SEMANTIC_MARGIN carries. Proceeds if either
            # signal clears its own floor.
            dense = Index(candidates).search(ask, top_k=1)[0]["dense"]
            semantic_score = SemanticIndex(candidates).search(ask, top_k=1)[0]["score"]
            if dense < min_dense_score and semantic_score < SEMANTIC_SINGLE_FLOOR:
                return {
                    "path": trace,
                    "leaf": None,
                    "leaf_passages": [],
                    "abstain_reason": (
                        f"only one {child_level} candidate and neither signal cleared its floor "
                        f"(dense {dense:.4f} < {min_dense_score}, semantic {semantic_score:.4f} < {SEMANTIC_SINGLE_FLOOR}) "
                        "-- no margin was computable to check instead"
                    ),
                }
            chosen = node.children[0]
            trace.append(
                {
                    "level": chosen.level,
                    "chosen": chosen.title,
                    "chosen_id": chosen.node_id,
                    "dense": round(dense, 4),
                    "semantic_score": round(semantic_score, 4),
                    "candidates_considered": 1,
                    "fallback": "single_candidate_dense_or_semantic_floor",
                }
            )
            node = chosen
            continue

        # top_k=len(candidates): dense_margin needs every candidate's dense
        # score to re-rank correctly, not just the top 2 by hybrid score.
        lexical_hits = Index(candidates).search(ask, top_k=len(candidates))
        semantic_hits = SemanticIndex(candidates).search(ask, top_k=2)
        lexical_margin = dense_margin(lexical_hits)
        # "Confident" requires clearing the floor (there's some real match at
        # all) AND a real margin over the runner-up (it isn't just generic
        # vocabulary every candidate shares, EXP-071) -- a floor alone let a
        # technically-nonzero, actually-noise lexical score veto a decisive
        # semantic one.
        lexical_abstain = lexical_hits[0]["dense"] < min_dense_score or lexical_margin < MIN_LEXICAL_MARGIN
        semantic_margin = semantic_hits[0]["score"] - semantic_hits[1]["score"]
        semantic_abstain = semantic_margin < min_margin
        lexical_top_id = lexical_hits[0]["passage"]["id"]
        semantic_top_id = semantic_hits[0]["passage"]["id"]

        if lexical_abstain and semantic_abstain:
            return {
                "path": trace,
                "leaf": None,
                "leaf_passages": [],
                "abstain_reason": f"neither lexical nor semantic retrieval found a confident {child_level} (lexical dense {lexical_hits[0]['dense']:.4f}, margin {lexical_margin:.4f}; semantic margin {semantic_margin:.4f})",
            }
        if not lexical_abstain and not semantic_abstain and lexical_top_id != semantic_top_id:
            return {
                "path": trace,
                "leaf": None,
                "leaf_passages": [],
                "abstain_reason": f"lexical and semantic retrieval disagree on which {child_level} matches ({lexical_top_id!r} vs {semantic_top_id!r})",
            }

        best_id = semantic_top_id if lexical_abstain else lexical_top_id
        chosen = next(child for child in node.children if child.node_id == best_id)
        trace.append(
            {
                "level": chosen.level,
                "chosen": chosen.title,
                "chosen_id": chosen.node_id,
                "lexical_dense": round(lexical_hits[0]["dense"], 4),
                "lexical_margin": round(lexical_margin, 4),
                "lexical_abstain": lexical_abstain,
                "semantic_margin": round(semantic_margin, 4),
                "semantic_abstain": semantic_abstain,
                "candidates_considered": len(candidates),
            }
        )
        node = chosen
    return {"path": trace, "leaf": node, "leaf_passages": node.leaf_passages}
