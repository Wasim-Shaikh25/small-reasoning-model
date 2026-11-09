"""A DIRECTED relationship graph over facts, with cycle detection.

`lab.common.graph_index.build_entity_graph` already answers "which facts
touch the same entities, possibly several hops apart" -- tested live
(2026-11-09) and confirmed correct on both a direct co-mention and a
genuine 2-hop case with no direct co-mention at all. But that graph is
undirected and untyped: it only knows two entities co-occurred in a
passage, not who did what to whom. "X gave Y money, Y gave Z money, Z
gave X money -- there is a relationship between X and Z" is a claim about
DIRECTION (who paid whom) forming a closed LOOP, which an undirected
co-occurrence edge cannot represent (it would connect X and Z the same
way it connects two people who merely appear in the same sentence for any
reason).

Direction is already recoverable, just from a different existing
primitive: `lab.common.rules.extract_fact_triple`'s subject/object (not
touched here -- adding a field alongside it, never changing its existing
return shape, since lab.common.rules.apply_rule and answer_rule_question
already depend on that shape unchanged). Verified live: for three "X gave
Y $N" sentences, extract_fact_triple correctly recovered subject->object
for every one, and the three directed edges closed back into a real cycle
(Alice->Bob->Carol->Alice).

The gap found in that same test: extract_fact_triple's object is the
RECIPIENT ("Bob Jones" in "gave Bob Jones $500"), and the amount
("$500") is dropped entirely -- it's a second complement the triple
extractor was never built to carry. Fixed here, additively, by pulling
the amount separately via lab.common.entities.detect_primary (already
measured correctly matching "$500"-style spans) and attaching it to the
edge -- extract_fact_triple itself is unmodified.
"""

from __future__ import annotations

from collections import defaultdict

from lab.common.entities import detect_primary
from lab.common.rules import extract_fact_triple
from lab.common.textutil import normalize


def build_relationship_graph(passages: list[dict]) -> dict:
    """One directed edge per passage whose text parses as a fact triple
    with both a subject and an object. Returns
    {"edges": [{"from", "to", "from_text", "to_text", "verb", "amount",
    "passage_id"}, ...], "nodes": {key: display_text}}.

    Nodes are keyed on normalized exact span text, same substitute for
    "the system doesn't understand language" that graph_index.py already
    uses -- no model resolves whether two differently-phrased spans are
    the same entity.
    """
    edges = []
    nodes: dict[str, str] = {}
    for passage in passages:
        text = passage.get("text", "") or ""
        fact = extract_fact_triple(text)
        if not fact or not fact.get("subject") or not fact.get("object"):
            continue
        from_key, to_key = normalize(fact["subject"]), normalize(fact["object"])
        if not from_key or not to_key or from_key == to_key:
            continue
        nodes[from_key] = fact["subject"]
        nodes[to_key] = fact["object"]
        amounts = [m["text"] for m in detect_primary(text) if m["label"] == "amount"]
        edges.append({
            "from": from_key,
            "to": to_key,
            "from_text": fact["subject"],
            "to_text": fact["object"],
            "verb": fact["verb_lemma"],
            "amount": amounts[0] if amounts else None,
            "passage_id": passage.get("id"),
        })
    return {"edges": edges, "nodes": nodes}


def find_cycles(graph: dict, max_len: int = 6) -> list[list[dict]]:
    """Every elementary (no repeated node) directed cycle up to `max_len`
    edges, each returned as its ordered list of edge dicts.

    Brute-force DFS, bounded by `max_len` -- fine for the small fact-
    graphs this builds (one edge per passage), not meant for a
    general-purpose large-graph cycle finder. Abstains (returns []) if
    there are no edges at all, same as every other primitive in this
    project returning "nothing found" rather than guessing.
    """
    adjacency = defaultdict(list)
    for edge in graph["edges"]:
        adjacency[edge["from"]].append(edge)

    raw_cycles = []

    def dfs(start: str, node: str, path: list[dict], in_path: set[str]):
        for edge in adjacency.get(node, ()):
            if edge["to"] == start and path:
                raw_cycles.append(path + [edge])
                continue
            if edge["to"] in in_path or len(path) + 1 >= max_len:
                continue
            dfs(start, edge["to"], path + [edge], in_path | {edge["to"]})

    for start_node in graph["nodes"]:
        dfs(start_node, start_node, [], {start_node})

    # Dedupe rotations of the same cycle (DFS from each node on the loop
    # finds it once per starting point).
    seen = set()
    unique_cycles = []
    for cycle in raw_cycles:
        node_sequence = tuple(e["from"] for e in cycle)
        rotations = {node_sequence[i:] + node_sequence[:i] for i in range(len(node_sequence))}
        canonical = min(rotations)
        if canonical not in seen:
            seen.add(canonical)
            unique_cycles.append(cycle)
    return unique_cycles
