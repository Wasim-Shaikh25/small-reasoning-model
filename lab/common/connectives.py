"""General, grammar-driven detection of English logical/discourse
connectives -- replacing keyword-regex matching (lab.common.inference's
previous `_UNLESS_RE`, a literal substring match on the single word
"unless") with structural detection over spaCy's dependency parse, plus a
small, documented lemma/phrase -> operator lookup table spanning PDTB's
four top-level discourse-relation classes (Temporal, Contingency,
Comparison, Expansion; Prasad et al., PDTB 2.0) instead of one "exception"
bucket for every subordinator.

Grounding, not guesswork: English's closed-class set of discourse
connectives is small and already catalogued -- DiMLex-Eng (Das, Scheffler,
Bourgonje & Stede, 2018) lists 149 total, not "1000+". The hard part was
never enumerating the words; it is (a) detecting them structurally instead
of by substring, and (b) assigning the RIGHT logical operator, since
different connectives in even the same PDTB class need opposite treatment:
"unless" blocks its main clause if its own clause is true; "although"/
"even though"/"even if" do the OPPOSITE -- the main clause holds ANYWAY,
regardless of their own clause's truth; "until"/"before"/"after"/"once"
are about WHEN, not WHETHER, and this module does not pretend to reason
over that (see Operator.TEMPORAL_BOUND below); "because"/"since"/"as" name
a justification, never a gate that could block anything.

Empirical grounding for the DETECTION patterns themselves (checked against
spaCy's real output on 20 example sentences, one per connective, before
writing this -- see lab/exp_090_connective_detection/run.py -- not assumed
from the "mark+advcl" heuristic the literature itself warns has real
attachment variance):
  - Most subordinators (if, unless, although, though, because, since,
    until, before, after, once, the "as" in "as long as", the "that" in
    "provided that") surface as a token with dep_=="mark", attached to a
    clause whose own dep_ is "advcl" OR "pcomp" (not always advcl).
  - A second group (except, except that, despite, provided, the "in" in
    "in case") surfaces as dep_=="prep" instead, with the governed clause
    reached via that token's own "pcomp" or "pobj" child -- a genuinely
    different structural shape, not a variant of the first.
  - Coordinating connectives (and, or) surface as dep_=="cc", but NOT
    reliably attached to the sentence's ROOT verb -- "or" between two
    full clauses was measured attaching to a noun object instead, a real,
    reported attachment ambiguity, not hidden.
  - "even"/"only" immediately before a mark token change the connective's
    meaning (if -> even if = concession, not condition) without changing
    its dependency label, so they are checked as a left neighbor, not
    folded into the lemma table.

Explicitly NOT attempted: discourse relations with no explicit connective
at all (PDTB's "Implicit" and "AltLex" categories, the majority of
relations in the actual PDTB corpus) are out of scope -- this module only
ever fires on a connective it can actually see a token for.
"""

from __future__ import annotations

from dataclasses import dataclass

from lab.common.rules import _parser


class Operator:
    """What a connective's own clause DOES to the clause it attaches to --
    never a single "exception" bucket, because that was simply wrong for
    most of these."""

    CONDITION_POSITIVE = "condition_positive"  # if, provided that, only if, as long as, in case
    CONDITION_NEGATIVE = "condition_negative"  # unless, except, except that -- blocks if true
    CONCESSION = "concession"  # although, though, even though, even if, despite -- holds ANYWAY
    TEMPORAL_BOUND = "temporal_bound"  # until, before, after, once -- WHEN, not WHETHER; not reasoned over here
    CAUSAL = "causal"  # because, since, as -- a justification, never a gate
    COMBINATOR_AND = "combinator_and"
    COMBINATOR_OR = "combinator_or"


# phrase (space-joined, lowercase surface form) -> (operator, pdtb_class).
# Scoped to ~20 of the highest-frequency, least class-ambiguous English
# connectives (chosen from DiMLex-Eng/PDTB, not invented), covering all
# four PDTB top-level classes plus the two combinators -- not the full
# 149-item inventory. A connective not in this table is reported as
# unrecognized (operator=None), never silently dropped or forced into the
# wrong bucket.
CONNECTIVE_TABLE: dict[str, tuple[str, str]] = {
    "if": (Operator.CONDITION_POSITIVE, "Contingency.Condition"),
    "provide that": (Operator.CONDITION_POSITIVE, "Contingency.Condition"),  # spaCy lemmatizes "provided" (VERB) to "provide"
    "only if": (Operator.CONDITION_POSITIVE, "Contingency.Condition"),
    "as long as": (Operator.CONDITION_POSITIVE, "Contingency.Condition"),
    "in case": (Operator.CONDITION_POSITIVE, "Contingency.Condition"),
    "unless": (Operator.CONDITION_NEGATIVE, "Contingency.Condition"),
    "except": (Operator.CONDITION_NEGATIVE, "Contingency.Condition"),
    "except that": (Operator.CONDITION_NEGATIVE, "Contingency.Condition"),
    "although": (Operator.CONCESSION, "Comparison.Concession"),
    "though": (Operator.CONCESSION, "Comparison.Concession"),
    "even though": (Operator.CONCESSION, "Comparison.Concession"),
    "even if": (Operator.CONCESSION, "Comparison.Concession"),
    "despite": (Operator.CONCESSION, "Comparison.Concession"),
    "until": (Operator.TEMPORAL_BOUND, "Temporal"),
    "before": (Operator.TEMPORAL_BOUND, "Temporal"),
    "after": (Operator.TEMPORAL_BOUND, "Temporal"),
    "once": (Operator.TEMPORAL_BOUND, "Temporal"),
    "because": (Operator.CAUSAL, "Contingency.Cause"),
    "since": (Operator.CAUSAL, "Contingency.Cause"),  # class-ambiguous with Temporal; see module docstring
    "as": (Operator.CAUSAL, "Contingency.Cause"),  # highly polysemous; only reached when dep_=="mark" (see below)
    # EXP-096: verified via the same mark+advcl pattern as "although" (checked
    # directly against spaCy output before adding, same as every entry above).
    "while": (Operator.CONCESSION, "Comparison.Concession"),
    "whereas": (Operator.CONCESSION, "Comparison.Concession"),
}

COMBINATOR_TABLE: dict[str, str] = {"and": Operator.COMBINATOR_AND, "or": Operator.COMBINATOR_OR}

# Sentence-initial discourse ADVERBIALS (EXP-050): a genuinely different
# structural category from CONNECTIVE_TABLE's intra-sentential
# subordinators -- "however"/"therefore" don't attach a dependent clause
# to a head the way "unless" does; they're their sentence's own ROOT's
# advmod child, checked empirically (lab/exp_050_neighbor_coherence/
# run.py): "However"/"Therefore"/"Moreover"/"Nevertheless" each surface as
# dep_=="advmod", head.dep_=="ROOT", token index 0 -- sentence-initial,
# never mid-clause, which is exactly what rules out the false-positive
# case of these same words used as ordinary adverbs elsewhere in a
# sentence ("the ruling was, however, overturned" is NOT detected here --
# correctly, since that "however" is not sentence-initial and this
# module does not claim to handle it). Mapped onto the SAME Operator
# values CONNECTIVE_TABLE already uses (not a new enum) since their
# logical role is the same discourse relation, just expressed between two
# full sentences instead of within one: however/nevertheless contrasts
# (CONCESSION's role); therefore/thus/consequently/hence names a result
# (CAUSAL's role, never a gate); moreover/furthermore adds on
# (COMBINATOR_AND's role).
DISCOURSE_ADVERBIAL_TABLE: dict[str, tuple[str, str]] = {
    "however": (Operator.CONCESSION, "Comparison.Concession"),
    "nevertheless": (Operator.CONCESSION, "Comparison.Concession"),
    "therefore": (Operator.CAUSAL, "Contingency.Cause"),
    "thus": (Operator.CAUSAL, "Contingency.Cause"),
    "consequently": (Operator.CAUSAL, "Contingency.Cause"),
    "hence": (Operator.CAUSAL, "Contingency.Cause"),
    "moreover": (Operator.COMBINATOR_AND, "Expansion.Conjunction"),
    "furthermore": (Operator.COMBINATOR_AND, "Expansion.Conjunction"),
    # EXP-096: verified via the same sentence-initial advmod+ROOT pattern,
    # checked directly before adding, same as every entry above.
    "meanwhile": (Operator.TEMPORAL_BOUND, "Temporal"),
    "subsequently": (Operator.TEMPORAL_BOUND, "Temporal"),
    "accordingly": (Operator.CAUSAL, "Contingency.Cause"),
    "additionally": (Operator.COMBINATOR_AND, "Expansion.Conjunction"),
    "similarly": (Operator.COMBINATOR_AND, "Expansion.Conjunction"),
    "likewise": (Operator.COMBINATOR_AND, "Expansion.Conjunction"),
    "conversely": (Operator.CONCESSION, "Comparison.Concession"),
}
# "in addition" is the same prep+pobj structural shape as "in case"
# (below), sentence-initial -- a second idiom for the same "in" token,
# not a new pattern.
_IN_IDIOMS: dict[str, tuple[str, str] | None] = {"case": None, "addition": (Operator.COMBINATOR_AND, "Expansion.Conjunction")}

_MARK_HEAD_DEPS = {"advcl", "pcomp", "relcl"}
# "ccomp" (a verb's own reported-speech/that-clause object, e.g. "demonstrate
# THAT X", "ascertain WHETHER Y") deliberately excluded -- measured directly
# against the real GDPR text (lab/exp_090_connective_detection/run.py): every
# "mark"+"ccomp" match found there was a pure complementizer ("that",
# "whether") introducing a verb's object clause, never a genuine discourse
# connective, and none of this module's 20 target connectives ever surface
# with head.dep_=="ccomp". A reported-speech complementizer is a different
# grammatical category from an adverbial discourse relation, not an unknown
# instance of one.
_PREP_SUBORDINATORS = {"except", "despite", "provide", "in", "until", "before", "after"}  # "provide": spaCy's lemma for "provided" (VERB)
# "until"/"before"/"after" (EXP-097's own bug, not a new finding at design
# time): these three surface as dep_=="mark" ONLY when their object is a
# clause with its own verb ("until the data subject withdraws consent").
# When the object is a bare date/noun phrase instead ("until 1 January
# 2020"), spaCy attaches them as an ordinary dep_=="prep" with a pobj
# child -- the SAME prep+pobj shape "except"/"despite" already use, not a
# new pattern, just never extended to this table until the gap surfaced:
# find_temporal_bound silently returned None for every absolute-date rule
# (mark+advcl was the only branch checked), so EXP-097's own case 1 went
# through un-gated. "once" deliberately excluded: "once <NP>" with no verb
# is not an attested English construction, so there is no prep-shaped gap
# to close for it.
_EMPHASIS_PREFIXES = {"even", "only"}


@dataclass
class ConnectiveMatch:
    phrase: str
    operator: str | None
    pdtb_class: str | None
    dep_pattern: str
    anchor_text: str
    clause_text: str


def _span_text(token) -> str:
    return " ".join(t.text for t in sorted(token.subtree, key=lambda t: t.i))


def _clause_text_for_prep(tok) -> tuple[str, str]:
    """The clause a prep-headed subordinator governs is its own pcomp or
    pobj child, not necessarily a child with a verb in its own subtree
    (measured directly: "despite" attaches its object as pobj, but the
    actual gerund clause sits elsewhere in the parse, a real spaCy
    attachment quirk for this construction, reported here rather than
    hidden). Falls back to the remainder of the sentence from this token
    onward when the chosen child's own subtree has no verb -- an
    approximate, non-syntactic span, visibly labeled as a fallback in the
    returned dep_pattern, never presented as equivalent to a clean parse.
    """
    child = next((c for c in tok.children if c.dep_ in ("pcomp", "pobj")), None)
    if child is None:
        return "", "no_clause_child"
    if any(t.pos_ in ("VERB", "AUX") for t in child.subtree):
        return _span_text(child), child.dep_
    doc = child.doc
    remainder = " ".join(t.text for t in doc[tok.i + 1 :])
    return remainder, f"{child.dep_}+fallback_remainder"


def find_connectives(text: str) -> list[ConnectiveMatch]:
    """Every logical/discourse connective this module recognizes in
    `text`, found by walking spaCy's dependency parse -- never by scanning
    the raw string for a keyword. A connective whose structural pattern is
    recognized (mark+advcl/pcomp, prep+pcomp/pobj, or cc) but whose
    phrase/lemma is not in CONNECTIVE_TABLE/COMBINATOR_TABLE is still
    returned, with operator=None, so a caller can tell "no connective
    here" apart from "a connective is here but this module doesn't know
    what it means yet" -- the same honest-abstention posture
    check_exception already applies to NLI uncertainty.
    """
    doc = _parser()(text)
    matches: list[ConnectiveMatch] = []
    consumed: set[int] = set()

    for tok in doc:
        if tok.i in consumed:
            continue

        if tok.i == 0 and tok.dep_ == "advmod" and tok.head.dep_ == "ROOT" and tok.lemma_.lower() in DISCOURSE_ADVERBIAL_TABLE:
            info = DISCOURSE_ADVERBIAL_TABLE[tok.lemma_.lower()]
            consumed.add(tok.i)
            matches.append(
                ConnectiveMatch(
                    phrase=tok.lemma_.lower(),
                    operator=info[0],
                    pdtb_class=info[1],
                    dep_pattern="advmod+ROOT",
                    anchor_text=tok.text,
                    clause_text=_span_text(tok.head),
                )
            )
            continue

        if tok.dep_ == "mark" and tok.head.dep_ in _MARK_HEAD_DEPS:
            phrase_tokens = [tok]
            if tok.lemma_.lower() == "as" and tok.i >= 2 and doc[tok.i - 1].lemma_.lower() == "long" and doc[tok.i - 2].lemma_.lower() == "as":
                phrase_tokens = [doc[tok.i - 2], doc[tok.i - 1], tok]
            else:
                prev = doc[tok.i - 1] if tok.i > 0 else None
                if prev is not None and prev.dep_ == "advmod" and prev.lemma_.lower() in _EMPHASIS_PREFIXES:
                    phrase_tokens.insert(0, prev)
            phrase = " ".join(t.lemma_.lower() for t in phrase_tokens)
            consumed.update(t.i for t in phrase_tokens)
            info = CONNECTIVE_TABLE.get(phrase) or CONNECTIVE_TABLE.get(tok.lemma_.lower())
            matches.append(
                ConnectiveMatch(
                    phrase=phrase,
                    operator=info[0] if info else None,
                    pdtb_class=info[1] if info else None,
                    dep_pattern=f"mark+{tok.head.dep_}",
                    anchor_text=" ".join(t.text for t in phrase_tokens),
                    clause_text=_span_text(tok.head),
                )
            )
            continue

        if tok.dep_ == "prep" and tok.lemma_.lower() in _PREP_SUBORDINATORS:
            phrase_tokens = [tok]
            nxt = doc[tok.i + 1] if tok.i + 1 < len(doc) else None
            if tok.lemma_.lower() == "in":
                if nxt is None or nxt.lemma_.lower() not in _IN_IDIOMS:
                    continue  # a plain "in" prepositional phrase, not a recognized "in <word>" idiom
                phrase_tokens.append(nxt)
            elif tok.lemma_.lower() in ("except", "provide") and nxt is not None and nxt.lemma_.lower() == "that":
                phrase_tokens.append(nxt)
            phrase = " ".join(t.lemma_.lower() for t in phrase_tokens)
            consumed.update(t.i for t in phrase_tokens)
            clause_text, dep_detail = _clause_text_for_prep(tok)
            info = CONNECTIVE_TABLE.get(phrase) or CONNECTIVE_TABLE.get(tok.lemma_.lower()) or (_IN_IDIOMS.get(nxt.lemma_.lower()) if nxt is not None else None)
            matches.append(
                ConnectiveMatch(
                    phrase=phrase,
                    operator=info[0] if info else None,
                    pdtb_class=info[1] if info else None,
                    dep_pattern=f"prep+{dep_detail}",
                    anchor_text=" ".join(t.text for t in phrase_tokens),
                    clause_text=clause_text,
                )
            )
            continue

        if tok.dep_ == "cc" and tok.lemma_.lower() in COMBINATOR_TABLE:
            matches.append(
                ConnectiveMatch(
                    phrase=tok.lemma_.lower(),
                    operator=COMBINATOR_TABLE[tok.lemma_.lower()],
                    pdtb_class="Expansion.Conjunction" if tok.lemma_.lower() == "and" else "Contingency.Condition",
                    dep_pattern="cc",
                    anchor_text=tok.text,
                    clause_text=_span_text(tok.head),
                )
            )
            continue

    return matches
