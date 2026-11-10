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

Follow-up (2026-11-10): HANDOFF.md's redesign proposal named the actual
fix for the adversarial case -- "bind this unresolved reference to the
best-supported node", scored by recency, embedding similarity AND role
compatibility, not recency alone. `_bind_reference`/`_score_candidate`
below implement that, with one correction found by testing (see
`_score_candidate`'s own docstring): a candidate carries the
GRAMMATICAL ROLE (subject/object/none) it played in its own source
sentence, but the right signal is SALIENCE (was this candidate a stated
argument of the previous fact at all), not role-PARALLELISM (does it
match the SAME role the pronoun plays) -- parallelism was tried first
and found to break this project's own motivating payment-chain example,
where the correct antecedent is deliberately the previous OBJECT, not a
same-role SUBJECT. A soft type-compatibility score ("it"/"its" prefers
an organization antecedent, "he"/"she"/... prefers a person) and an
optional bge-embedding-similarity tiebreak (`use_embedding_tiebreak`)
round out the score; this is a closed, generic fact about English
discourse structure, the same class of exception this project already
carves out for pronoun lists and POS-tag categories -- not a domain
guess. Re-ran both named test cases (see AUDIT.md, "generic reference
binder, replacing the pronoun-only recency heuristic"): the
straightforward/payment-chain case still resolves correctly (salience
ties, recency still breaks it the same way the old heuristic did), and
the adversarial case -- which the old heuristic got WRONG -- now
resolves correctly too, because the true antecedent (a real argument of
the previous fact) outscores the closer but non-argument incidental
mention on salience.

Kept, not deleted: `_resolve_antecedent` (the old recency-only
heuristic) stays as the default -- `build_relationship_graph`'s new
`use_reference_binder` parameter defaults to False, so no existing
caller's measured output changes unless it opts in, same discipline as
every other flag in this project. HANDOFF.md's own instruction: "keep
the old heuristic as a fallback until the generic version is measured
to beat it on a labeled set" -- there is no real labeled set here (two
hand-built test cases, not a corpus), so this is reported as a directly
measured improvement on the two known failure shapes, not a general
accuracy claim.
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


# A closed fact about English pronouns' natural gender/type class (not a
# domain guess) -- "they"/"them"/"their"/"theirs" and "that"/"this" stay
# out of this map deliberately: they are genuinely type-neutral (a
# singular-person "they" is common; "that"/"this" can stand in for either).
_PRONOUN_TYPE_HINT = {
    "he": "person", "him": "person", "his": "person",
    "she": "person", "her": "person", "hers": "person",
    "it": "organization", "its": "organization",
}


def _score_candidate(
    candidate: dict,
    pronoun: str,
    rank: int,
    total: int,
    context_text: str,
    use_embedding_tiebreak: bool,
) -> float:
    """Higher is a better antecedent guess.

    First version of this scorer tried "role-parallelism" (prefer a
    candidate whose own role matches the role the pronoun itself plays,
    e.g. a subject pronoun prefers a previous SUBJECT) as the dominant
    signal. Tested directly against this project's own two named cases
    and found WRONG on the first one: this project's own motivating
    example is a payment CHAIN ("X gave Y money, Y gave Z money, Z gave X
    money"), where the correct antecedent for the next sentence's subject
    pronoun is deliberately the PREVIOUS sentence's OBJECT (the chain
    hands the topic off), not a same-role match. Parallelism is a real
    heuristic in the coreference literature, but it is genre-dependent,
    and this project's own primary demonstrated capability (the 3-party
    cycle) is exactly the genre it gets backwards -- so it is not used.

    The signal that actually generalizes across both named cases is
    SALIENCE, not role-matching: a candidate that was itself a stated
    argument (subject OR object) of the immediately preceding fact triple
    is a far more available antecedent than one merely NAMED inside an
    incidental/subordinate clause the triple extractor didn't bind at
    all (centering theory ranks any realized grammatical argument above
    a non-argument mention, without requiring the SAME argument slot).
    Verified directly: in the payment-chain case both the previous
    subject and object are salient (role is not None), so salience alone
    doesn't discriminate between them and recency correctly breaks the
    tie in the object's favor, same as the old heuristic; in the
    subordinate-clause adversarial case, the incidental mention has no
    recognized role at all (salience 0), so the true, salient-but-less-
    recent antecedent wins even though it is textually farther away.

    Type compatibility is a soft secondary filter (downweighted on a
    mismatch, never zero-filtered, so this never regresses to "abstain"
    when every real candidate happens to mismatch); an optional
    bge-embedding similarity between the pronoun's own sentence and the
    candidate's source sentence is the weakest-weighted signal, only
    computed when `use_embedding_tiebreak` is set (an extra model call
    per resolution, opt-in for exactly that cost reason).
    """
    salience_score = 1.0 if candidate.get("role") is not None else 0.0
    type_hint = _PRONOUN_TYPE_HINT.get(pronoun)
    type_score = 1.0 if not type_hint or candidate.get("label") == type_hint else 0.0
    recency_score = (rank + 1) / total
    embedding_score = 0.0
    if use_embedding_tiebreak and context_text and candidate.get("source_text"):
        from lab.common.real_encoders import bge_similarity

        embedding_score = bge_similarity(context_text, candidate["source_text"])
    return 3.0 * salience_score + 1.5 * type_score + 1.0 * recency_score + 1.0 * embedding_score


def _bind_reference(
    span: str,
    candidates: list[dict],
    context_text: str = "",
    use_embedding_tiebreak: bool = False,
) -> dict:
    """The generic replacement for `_resolve_antecedent`: scores every
    candidate (see `_score_candidate`) instead of always picking "whatever
    was mentioned last". Returns the same `{"text", "pronoun_resolved",
    "ambiguous", "alternatives"}` shape, so a caller doesn't need to know
    which binder actually ran.
    """
    if normalize(span) not in _PRONOUNS or not candidates:
        return {"text": span, "pronoun_resolved": False, "ambiguous": False, "alternatives": []}
    pronoun = normalize(span)
    scored = [
        (c, _score_candidate(c, pronoun, i, len(candidates), context_text, use_embedding_tiebreak))
        for i, c in enumerate(candidates)
    ]
    scored.sort(key=lambda pair: pair[1])
    best_candidate = scored[-1][0]
    return {
        "text": best_candidate["text"],
        "pronoun_resolved": True,
        "ambiguous": len(candidates) > 1,
        "alternatives": [c["text"] for c, _ in scored[:-1]],
    }


def build_relationship_graph(passages: list[dict], use_reference_binder: bool = False, use_embedding_tiebreak: bool = False) -> dict:
    """One directed edge per passage whose text parses as a fact triple
    with both a subject and an object. Returns
    {"edges": [{"from", "to", "from_text", "to_text", "verb", "amount",
    "passage_id"}, ...], "nodes": {key: display_text}}.

    Nodes are keyed on normalized exact span text, same substitute for
    "the system doesn't understand language" that graph_index.py already
    uses -- no model resolves whether two differently-phrased spans are
    the same entity, except for the one pronoun case handled by
    `_resolve_antecedent` (default) or `_bind_reference`
    (`use_reference_binder=True`) above.
    """
    edges = []
    nodes: dict[str, str] = {}
    recent_mentions: list[str] = []
    recent_candidates: list[dict] = []
    for passage in passages:
        text = passage.get("text", "") or ""
        fact = extract_fact_triple(text)
        real_mentions = [m["text"] for m in detect_primary(text) if m["label"] in ("person", "organization")]
        tagged_candidates = []
        for m in detect_primary(text):
            if m["label"] not in ("person", "organization"):
                continue
            role = None
            if fact:
                if normalize(m["text"]) == normalize(fact.get("subject") or ""):
                    role = "subject"
                elif normalize(m["text"]) == normalize(fact.get("object") or ""):
                    role = "object"
            tagged_candidates.append({"text": m["text"], "label": m["label"], "role": role, "source_text": text})
        if not fact or not fact.get("subject") or not fact.get("object"):
            if real_mentions:
                recent_mentions = real_mentions
                recent_candidates = tagged_candidates
            continue

        if use_reference_binder:
            subject_resolution = _bind_reference(fact["subject"], recent_candidates, context_text=text, use_embedding_tiebreak=use_embedding_tiebreak)
        else:
            subject_resolution = _resolve_antecedent(fact["subject"], recent_mentions)
        subject_text = subject_resolution["text"]
        object_resolution = {"text": fact["object"], "pronoun_resolved": False, "ambiguous": False, "alternatives": []}
        if normalize(fact["object"]) in _PRONOUNS:
            # Never resolve the object to the same entity just picked for
            # the subject -- "he gave him money" needs two DIFFERENT
            # antecedents, and this heuristic has only one to offer, so it
            # abstains (keeps the raw pronoun span) rather than guess a
            # self-loop.
            if use_reference_binder:
                candidate = _bind_reference(fact["object"], recent_candidates, context_text=text, use_embedding_tiebreak=use_embedding_tiebreak)
            else:
                candidate = _resolve_antecedent(fact["object"], recent_mentions)
            if normalize(candidate["text"]) != normalize(subject_text):
                object_resolution = candidate
        object_text = object_resolution["text"]

        from_key, to_key = normalize(subject_text), normalize(object_text)
        if real_mentions:
            recent_mentions = real_mentions
            recent_candidates = tagged_candidates
        elif normalize(subject_text) not in _PRONOUNS:
            recent_mentions = [subject_text]
            recent_candidates = [{"text": subject_text, "label": "person", "role": "subject", "source_text": text}]
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
