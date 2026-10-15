"""Hierarchical (nested) navigation over a large document, so a 1000-page
document is searched level by level -- book -> chapter -> section -> leaf --
instead of flattened into one giant list the way `lab.common.index.Index`
and `lab.common.assemble.build_outline` currently do.

Design choice, stated rather than silently made: navigation (which branch to
descend into) is decided by the existing hybrid retriever
(`lab.common.index.Index`), the same embeddings-and-BM25 mechanism already
proven at scale (EXP-004/015/029/040), not by the generative rewriter. Every
measurement in this project so far says Gemma/flan-t5-small are reliable at
one thing -- rewriting a small, already-resolved slice -- and unreliable at
anything resembling search or multi-step judgment. Making Gemma "navigate"
would be re-introducing exactly the failure mode the rest of this project has
spent many explorations designing around. What Gemma (or a human) gets
instead is the full navigation path this module produces: an explicit,
inspectable trace of which node was chosen at every level and why, in the
same spirit as `lab.common.brain`'s trace -- multi-step thinking that is
visible, not a black box, even though no step in it is a language-model
judgment call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lab.common.index import Index


@dataclass
class NestedNode:
    node_id: str
    level: str
    title: str
    summary_text: str
    children: list["NestedNode"] = field(default_factory=list)
    leaf_passages: list[dict] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children


def build_nested_index(items: list[dict], level_keys: list[str]) -> NestedNode:
    """Build a tree from flat records, grouping by `level_keys` in order.

    Each item needs an "id", a "text", and one key per entry in `level_keys`
    (e.g. ["chapter", "section"]) naming which branch it belongs to at each
    level. A node's `summary_text` -- what navigation actually matches the
    ask against -- is the concatenation of its children's titles/summaries,
    never the raw leaf text pulled up a level; a chapter is findable by what
    its sections are about, not by every sentence inside them bleeding
    upward.
    """
    root = NestedNode(node_id="root", level="root", title="root", summary_text="")
    _insert_all(root, items, level_keys)
    _fill_summaries(root)
    return root


def _insert_all(root: NestedNode, items: list[dict], level_keys: list[str]) -> None:
    by_path: dict[tuple, NestedNode] = {(): root}
    for item in items:
        path = tuple(item[key] for key in level_keys)
        for depth in range(1, len(path) + 1):
            prefix = path[:depth]
            if prefix in by_path:
                continue
            parent = by_path[prefix[:-1]]
            node = NestedNode(
                node_id="/".join(str(p) for p in prefix),
                level=level_keys[depth - 1],
                title=str(prefix[-1]),
                summary_text="",
            )
            parent.children.append(node)
            by_path[prefix] = node
        by_path[path].leaf_passages.append(item)


def _fill_summaries(node: NestedNode) -> None:
    if node.is_leaf:
        node.summary_text = " ".join(p["text"] for p in node.leaf_passages)
        return
    for child in node.children:
        _fill_summaries(child)
    node.summary_text = " ".join(f"{child.title} {child.summary_text}" for child in node.children)


def navigate(ask: str, root: NestedNode, top_k: int = 1, min_dense_score: float = 1e-9) -> dict:
    """Descend the tree one level at a time, scoring each level's children
    against the ask with the hybrid retriever, until a leaf is reached.

    Returns {"path": [...], "leaf": NestedNode | None, "leaf_passages": [...]}.
    `path` is the full node-by-node trace -- every level's candidates and
    which one was chosen -- so the navigation is auditable even though it
    never involves a language model. Abstains (leaf=None) if a level's
    children can't be scored at all (e.g. an empty branch), or if the best
    candidate's *raw* dense (TF-IDF cosine) score is not strictly positive.

    Why a near-zero floor and not a magnitude-based one: a fixed absolute
    floor (0.05, even 0.01) does not survive scale -- as a chapter's summary
    grows (more leaves concatenated into it), a genuine needle's distinctive
    vocabulary becomes a shrinking fraction of the text, and the correct
    candidate's dense score shrinks with it (measured 0.64 -> 0.017 -> 0.0056
    across EXP-065's three sizes for the identical needle). A magnitude floor
    tuned on the small case wrongly rejects the correct answer at the larger
    ones. What does not shrink with scale is the *separation*: a genuine
    match, however diluted, always has a strictly positive dense score
    (TF-IDF cosine over any shared non-stopword vocabulary, however small a
    fraction of the summary), while a truly unrelated ask gives an exact
    mathematical 0.0 for every candidate -- disjoint sparse vectors have a
    dot product of exactly zero, not a small positive number. Why dense and
    not the blended `score`: the blended score is min-max normalized per
    level, so the single best candidate is stretched toward 1.0 even when
    nothing actually matches -- confirmed directly (EXP-065's off-topic ask
    scored 0.5 that way). The raw sparse (BM25) leg is also unreliable here
    because index.tokenize has no stopword filter, so "what"/"is"/"the"
    alone produce a nonzero BM25 score on pure noise.
    """
    trace = []
    node = root
    while not node.is_leaf:
        candidates = [{"id": child.node_id, "text": child.summary_text} for child in node.children]
        child_level = node.children[0].level
        index = Index(candidates)
        hits = index.search(ask, top_k=top_k)
        if not hits:
            return {"path": trace, "leaf": None, "leaf_passages": [], "abstain_reason": f"no {child_level} candidates to score"}
        if hits[0]["dense"] < min_dense_score:
            return {
                "path": trace,
                "leaf": None,
                "leaf_passages": [],
                "abstain_reason": f"no {child_level} scored above the dense-similarity floor (best: {hits[0]['dense']:.4f} < {min_dense_score})",
            }
        best_id = hits[0]["passage"]["id"]
        chosen = next(child for child in node.children if child.node_id == best_id)
        trace.append(
            {
                "level": chosen.level,
                "chosen": chosen.title,
                "chosen_id": chosen.node_id,
                "score": round(hits[0]["score"], 4),
                "candidates_considered": len(candidates),
            }
        )
        node = chosen
    return {"path": trace, "leaf": node, "leaf_passages": node.leaf_passages}
