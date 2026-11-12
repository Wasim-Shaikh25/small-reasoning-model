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

# A genuine TF-IDF match always has a strictly positive dense score (shared
# non-stopword vocabulary, however small a fraction); true noise is exactly
# 0.0 (disjoint sparse vectors dot-product to exactly zero). Exposed as a
# named constant so lab.common.brain's flat disambiguation can reuse the
# identical, already-measured floor instead of redefining its own copy.
MIN_DENSE_SCORE = 1e-9


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


# The lexical-only `navigate` descent that used to live here moved to
# lab.tests.support on 2026-11-12 -- lab.common.brain's hierarchical_navigate
# stage calls navigate_dual (lab.common.semantic_index), not this. navigate
# stays reachable from lab.tests.support for EXP-065/067/070's own
# comparison against navigate_dual.
