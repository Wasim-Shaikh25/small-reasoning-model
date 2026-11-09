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

Follow-up (same day): user asked what happens when "Smith" is later
referred to as "she" or another pronoun rather than by name again.
Confirmed live this broke cycle detection completely (a pronoun subject
normalizes to its own node, e.g. "he", disconnected from the real
entity). Fixed with a nearest-antecedent heuristic (see
`_resolve_antecedent`) -- confirmed working on the straightforward case,
and confirmed WRONG on a harder adversarial case built specifically to
find the failure (the true antecedent was the previous clause's subject,
not its most recently named entity). User's call on the resulting
tradeoff: keep guessing rather than abstain, but every edge whose
subject or object was resolved from >1 plausible candidate is tagged
`antecedent_ambiguous: True` with the candidates it picked between in
`antecedent_alternatives` -- so a caller can tell a confident resolution
from a guess, without the module either silently dropping correct
connections or silently trusting wrong ones.
"""

from __future__ import annotations

from collections import defaultdict

from lab.common.entities import detect_primary
from lab.common.rules import extract_fact_triple
from lab.common.textutil import normalize

# Bare pronouns extract_fact_triple will happily return as a "subject" or
# "object" span (it only parses dependency structure, it doesn't know these
# aren't names). Resolved below by a nearest-antecedent heuristic -- NOT
# true coreference. "that"/"this" are included for a demonstrative used as
# a stand-in for a person ("that one paid Carol"), not for every
# determiner use ("that payment").
_PRONOUNS = {
    "he", "him", "his", "she", "her", "hers",
    "it", "its", "they", "them", "their", "theirs",
    "that", "this",
}


def _resolve_antecedent(span: str, recent_mentions: list[str]) -> dict:
    """Nearest-antecedent heuristic: a bare pronoun resolves to whichever
    real (non-pronoun) person/organization span was most recently seen,
    in passage order -- the simplest, best-known approximation for this
    problem, not true coreference resolution. No gender/number agreement
    is checked (none of this project's entity detection carries gender),
    so it WILL pick the wrong antecedent whenever the true referent isn't
    simply "whatever named entity appeared last" -- e.g. the previous
    sentence's object, not its subject, when the subject is who a
    following "she" actually meant. Known, named limit, not hidden; see
    AUDIT.md, "pronoun/coreference gap" (2026-11-09).

    User's own resolution of that tradeoff (asked directly, 2026-11-09):
    keep resolving by best guess rather than abstaining whenever more than
    one candidate exists, but never hide the uncertainty -- so this
    returns {"text", "pronoun_resolved", "ambiguous", "alternatives"}
    instead of a bare string: the guess is still made (so the
    straightforward, confirmed-working case keeps working), but a caller
    can see exactly which resolutions picked among >1 candidate, the same
    spirit as `entities.apply_ambiguity_rules` marking a shared-surname
    name "ambiguous" with alternatives rather than silently merging it.
    `recent_mentions` is every real entity span seen in the most recent
    passage that had any (order preserved); the last one is the guess,
    the rest are the alternatives it passed over.
    """
    if normalize(span) not in _PRONOUNS or not recent_mentions:
        return {"text": span, "pronoun_resolved": False, "ambiguous": False, "alternatives": []}
    return {
        "text": recent_mentions[-1],
        "pronoun_resolved": True,
        "ambiguous": len(recent_mentions) > 1,
        "alternatives": recent_mentions[:-1],
    }


def build_relationship_graph(passages: list[dict]) -> dict:
    """One directed edge per passage whose text parses as a fact triple
    with both a subject and an object. Returns
    {"edges": [{"from", "to", "from_text", "to_text", "verb", "amount",
    "passage_id"}, ...], "nodes": {key: display_text}}.

    Nodes are keyed on normalized exact span text, same substitute for
    "the system doesn't understand language" that graph_index.py already
    uses -- no model resolves whether two differently-phrased spans are
    the same entity, except for the one narrow pronoun case handled by
    `_resolve_antecedent` above.
    """
    edges = []
    nodes: dict[str, str] = {}
    recent_mentions: list[str] = []
    for passage in passages:
        text = passage.get("text", "") or ""
        fact = extract_fact_triple(text)
        real_mentions = [m["text"] for m in detect_primary(text) if m["label"] in ("person", "organization")]
        if not fact or not fact.get("subject") or not fact.get("object"):
            if real_mentions:
                recent_mentions = real_mentions
            continue

        subject_resolution = _resolve_antecedent(fact["subject"], recent_mentions)
        subject_text = subject_resolution["text"]
        object_resolution = {"text": fact["object"], "pronoun_resolved": False, "ambiguous": False, "alternatives": []}
        if normalize(fact["object"]) in _PRONOUNS:
            # Never resolve the object to the same entity just picked for
            # the subject -- "he gave him money" needs two DIFFERENT
            # antecedents, and this heuristic has only one to offer, so it
            # abstains (keeps the raw pronoun span) rather than guess a
            # self-loop.
            candidate = _resolve_antecedent(fact["object"], recent_mentions)
            if normalize(candidate["text"]) != normalize(subject_text):
                object_resolution = candidate
        object_text = object_resolution["text"]

        from_key, to_key = normalize(subject_text), normalize(object_text)
        if real_mentions:
            recent_mentions = real_mentions
        elif normalize(subject_text) not in _PRONOUNS:
            recent_mentions = [subject_text]
        if not from_key or not to_key or from_key == to_key:
            continue
        nodes[from_key] = subject_text
        nodes[to_key] = object_text
        amounts = [m["text"] for m in detect_primary(text) if m["label"] == "amount"]
        edges.append({
            "from": from_key,
            "to": to_key,
            "from_text": subject_text,
            "to_text": object_text,
            "verb": fact["verb_lemma"],
            "amount": amounts[0] if amounts else None,
            "passage_id": passage.get("id"),
            "antecedent_ambiguous": subject_resolution["ambiguous"] or object_resolution["ambiguous"],
            "antecedent_alternatives": subject_resolution["alternatives"] + object_resolution["alternatives"],
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
