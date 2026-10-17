"""An entity-relation graph over a document's passages, for the one gap
lab.common.nested_index structurally cannot close: combining facts about
the same entity when they live in two *different* branches of the tree
(different chapters, different flat groups).

nested_index.navigate / semantic_index.navigate_dual commit to one path
through the tree and return one leaf's passages -- by design, proven
useful (EXP-065 onward), but it means an ask needing a fact from chapter A
and a different fact about the same person from chapter B has no way to
get both. Classical and deterministic, same as every other retrieval
primitive in this repo (lab.common.index, lab.common.nested_index): no
model decides which entities are "the same" or which passages are related
-- exact-text matching on lab.common.entities' already-measured person/org
extraction decides that, the same substitute used everywhere else here.

A node is one entity's exact surface text (not resolved across spelling
variants -- lab.common.entities.resolve_mentions already exists for that
harder problem and is not reused here, to keep this one primitive doing
one bounded thing). An edge exists between two entities that co-occur in
the same passage. Expansion is breadth-first from a starting entity,
capped at max_hops, returning every passage touched along the way.
"""

from __future__ import annotations

from collections import defaultdict

from lab.common.entities import detect_primary
from lab.common.textutil import normalize

GRAPH_LABELS = ("person", "organization")


def build_entity_graph(passages: list[dict], use_real_ner: bool = False) -> dict:
    """Returns {"nodes": {entity_key: {"text", "label", "passage_ids": set}},
    "edges": {entity_key: set(other_entity_keys)}}.

    `use_real_ner` passes straight through to lab.common.entities.
    detect_primary -- see that function for why it defaults to False.
    """
    nodes: dict[str, dict] = {}
    edges: dict[str, set] = defaultdict(set)

    for passage in passages:
        mentions = [m for m in detect_primary(passage.get("text", ""), use_real_ner=use_real_ner) if m["label"] in GRAPH_LABELS]
        keys = []
        for mention in mentions:
            key = normalize(mention["text"])
            if not key:
                continue
            if key not in nodes:
                nodes[key] = {"text": mention["text"], "label": mention["label"], "passage_ids": set()}
            nodes[key]["passage_ids"].add(passage.get("id"))
            keys.append(key)
        for i, left in enumerate(keys):
            for right in keys[i + 1 :]:
                if left != right:
                    edges[left].add(right)
                    edges[right].add(left)

    return {"nodes": nodes, "edges": dict(edges)}


def find_entity_key(graph: dict, entity_text: str) -> str | None:
    key = normalize(entity_text)
    if key in graph["nodes"]:
        return key
    for candidate_key, node in graph["nodes"].items():
        if key and key in candidate_key:
            return candidate_key
    return None


def expand_from_entity(entity_text: str, graph: dict, passages_by_id: dict, max_hops: int = 1) -> dict:
    """Breadth-first expansion from `entity_text`'s node, capped at max_hops.

    Returns {"passages": [...], "path": [{"hop": n, "entity": ..., "via": ...}]} --
    `path` is the same kind of explicit, inspectable trace lab.common.brain's
    other steps already produce, not a black box.
    """
    start_key = find_entity_key(graph, entity_text)
    if start_key is None:
        return {"passages": [], "path": [], "abstain_reason": f"entity {entity_text!r} not found in the document's entity graph"}

    visited = {start_key}
    frontier = [start_key]
    path = [{"hop": 0, "entity": graph["nodes"][start_key]["text"], "via": None}]
    touched_passage_ids = set(graph["nodes"][start_key]["passage_ids"])

    for hop in range(1, max_hops + 1):
        next_frontier = []
        for key in frontier:
            for neighbor_key in graph["edges"].get(key, ()):
                if neighbor_key in visited:
                    continue
                visited.add(neighbor_key)
                next_frontier.append(neighbor_key)
                touched_passage_ids.update(graph["nodes"][neighbor_key]["passage_ids"])
                path.append({"hop": hop, "entity": graph["nodes"][neighbor_key]["text"], "via": graph["nodes"][key]["text"]})
        frontier = next_frontier
        if not frontier:
            break

    passages = [passages_by_id[pid] for pid in touched_passage_ids if pid in passages_by_id]
    return {"passages": passages, "path": path}
