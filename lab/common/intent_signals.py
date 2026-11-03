"""Domain-agnostic intent signals: does this ask want an identity, or a total?

Replaces two literal keyword checks that used to live in lab.common.brain --
a fixed TOTAL_CUES word list, and an identity check requiring the literal
substrings "name" and "address" -- plus, transitively, lab.common.ask's
ENTITY_CUES, which used to include "lessee"/"lessor": real lease-contract
vocabulary baked into what was supposed to be a domain-agnostic signal. Found
and removed after EXP-068 built a flat-disambiguation paraphrase case
("take-home pay", "where do they reside") whose disambiguation resolved
correctly but whose intent went unrecognized downstream, because neither
check's exact words were present.

Every exemplar sentence below describes a QUESTION FORM (who/where, or
how-much/total), never a subject domain -- the same form applies whether the
passages underneath are about a lease, a patient's medication, an insurance
claim, or an engineering inspection. Scored with bge (lab.common.real_encoders),
the same embedding checkpoint already used for semantic retrieval
(EXP-067/068): cosine similarity against a small set of exemplar phrasings,
not a literal substring match, so a paraphrase scores the same as the
exemplar's own wording would.

IDENTITY_TAU and TOTAL_TAU are EXP-069's measured values, calibrated against
asks from three domains nothing else in this repo had touched before that
exploration (medical, insurance, engineering) specifically so the threshold
isn't an artifact of the lease/contract wording every other fixture in this
project happens to use -- see that exploration before adjusting either value.
"""

from __future__ import annotations

import re

import numpy as np

from lab.common.real_encoders import bge_embed
from lab.common.rules import _parser

# A compound ask ("Who is X, and where do they live? What's their total,
# and does policy require approval?") scored as one whole string dilutes
# whichever clause actually carries the signal -- the same problem EXP-056
# already found for ask-relevance, resurfacing here (EXP-069). Splitting on
# sentence-ending punctuation always (pure punctuation, no word matched)
# and on the conjunction "and" only when it coordinates two independent
# clauses -- found structurally, not by a literal `\band\b` match (EXP-092:
# that old regex was the same class of hardcoding EXP-090/091/026 already
# removed from lab.common.inference, and wrong on top of it the same way --
# "What is their name and address?", one of this module's own
# IDENTITY_EXEMPLARS, is ONE clause with a compound object, and the old
# regex shredded it into "What is their name" / "address?").
_SENTENCE_SPLIT_RE = re.compile(r"[?.;]")  # pure punctuation -- no word is matched here


def _and_split_points(ask: str, doc) -> list[int]:
    """Token indices of every "and" that coordinates two independent
    clauses in `ask`, not a compound noun/noun-phrase sharing one verb --
    the same structural question lab.common.inference._clauses answers
    for rule consequences (EXP-026), but checked more permissively than
    that module needs to: a coordinated clause counts if its own "conj"
    sibling is itself a verb/auxiliary, OR has its own subject/auxiliary
    child, even when spaCy's statistical tagger mis-tags that sibling's
    own POS. Measured directly, not assumed: "What is the total amount,
    and does company policy require finance head approval?" -- EXP-094's
    own real ask text -- tags "require" as NOUN (not VERB) after the
    inverted "does X require Y" question structure, which a pure
    VERB/AUX-tag check (the rule inference.py's declarative-consequence
    clauses never needed to work around) would silently fail to split;
    "require" still carries an "aux" child ("does") and an "nsubj" child
    ("policy") regardless of its own mistagged POS, so checking for those
    children catches the real clause structure a tag alone misses.
    "What is their name and address?" has no such children on "address"
    at all, so it correctly still does not split.
    """
    points = []
    for tok in doc:
        if tok.dep_ != "cc" or tok.lemma_.lower() != "and":
            continue
        sibling = next((c for c in tok.head.children if c.dep_ == "conj"), None)
        if sibling is None:
            continue
        is_clause = sibling.pos_ in ("VERB", "AUX") or any(c.dep_ in ("nsubj", "nsubjpass", "aux", "auxpass") for c in sibling.children)
        if is_clause:
            points.append(tok.i)
    return points


def _clauses(ask: str) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(ask) if s.strip()]
    clauses: list[str] = []
    for sentence in sentences:
        doc = _parser()(sentence)
        split_points = _and_split_points(sentence, doc)
        if not split_points:
            clauses.append(sentence)
            continue
        start = 0
        for idx in split_points:
            clauses.append(doc[start:idx].text.strip())
            start = idx + 1
        clauses.append(doc[start:].text.strip())
    clauses = [c for c in clauses if c]
    return clauses or [ask]


IDENTITY_EXEMPLARS = (
    "Who is this person, and where are they located?",
    "What is their name and address?",
    "Which individual is involved, and what is their location?",
    "Identify the person and state where they live.",
)

TOTAL_EXEMPLARS = (
    "What is the total amount?",
    "How much is the combined sum?",
    "What is the sum of all the amounts?",
    "How much is there altogether?",
)

DOCUMENT_EXEMPLARS = (
    "Write a full report covering everyone.",
    "Draft a complete document summarizing all the findings.",
    "Compose a detailed write-up for each person.",
    "Produce a long-form summary document.",
)

RULE_EXEMPLARS = (
    "Does this comply with the rule?",
    "Is this action allowed under the policy?",
    "Does an exception apply to this prohibition?",
    "Is the conduct permitted or prohibited by this regulation?",
)

# MODEL-VERSION GUARD NOTE (2026-11-03 reasoning-layer audit, AUDIT.md):
# every threshold below was calibrated against bge_embed's checkpoint AT
# CALIBRATION TIME -- currently lab.common.real_encoders.BGE_MODEL_NAME =
# "BAAI/bge-small-en-v1.5". Nothing anywhere in this codebase asserts or
# logs which checkpoint actually produced a given score; if
# BGE_MODEL_NAME is ever changed, every one of these four thresholds
# silently miscalibrates with zero warning, catchable today only by
# manually rerunning EXP-069 (IDENTITY_TAU/TOTAL_TAU)/EXP-078
# (DOCUMENT_TAU)/EXP-084 (RULE_TAU)'s own fixtures by hand. Re-measure all
# four before changing BGE_MODEL_NAME, not just the ones you expect to be
# affected.
IDENTITY_TAU = 0.5971
TOTAL_TAU = 0.6084
# First measured value (lab.common.longform's wiring into brain.reason),
# not swept across multiple domains the way IDENTITY_TAU/TOTAL_TAU were
# (EXP-069) -- same caveat MIN_SEMANTIC_MARGIN/SEMANTIC_SINGLE_FLOOR carry:
# a starting point, checked against a handful of asks on both sides, not a
# validated constant. Measured range: 4 genuine document-requesting asks
# scored 0.838-0.889; 5 short-lookup asks scored 0.46-0.54, except one
# compound multi-clause lookup ask (EXP-069's engineering fixture) which
# scored 0.6621 -- comfortably below the document cluster, but well above
# a naive midpoint guess would have placed the floor, so this sits with a
# real margin on both sides rather than splitting the two clusters evenly.
DOCUMENT_TAU = 0.75
# EXP-084: first measured value, same caveat as DOCUMENT_TAU -- a starting
# point, not swept across domains the way IDENTITY_TAU/TOTAL_TAU were.
# Measured range: 4 genuine rule-compliance asks scored 0.6275-0.7443; 5
# non-rule asks (identity/total/document/plain-lookup, drawn from
# existing fixtures) scored 0.525-0.6039 -- a real gap between clusters
# (0.6039 vs 0.6275), not a coin-flip midpoint.
RULE_TAU = 0.62


def _best_similarity(text: str, exemplars: tuple[str, ...]) -> float:
    clauses = _clauses(text)
    vecs = bge_embed([*clauses, *exemplars])
    clause_vecs, exemplar_vecs = vecs[: len(clauses)], vecs[len(clauses) :]
    return float(np.max(clause_vecs @ exemplar_vecs.T))


def wants_identity(ask: str, tau: float = IDENTITY_TAU) -> dict:
    score = _best_similarity(ask, IDENTITY_EXEMPLARS)
    return {"fires": score >= tau, "score": round(score, 4), "tau": tau}


def wants_total(ask: str, tau: float = TOTAL_TAU) -> dict:
    score = _best_similarity(ask, TOTAL_EXEMPLARS)
    return {"fires": score >= tau, "score": round(score, 4), "tau": tau}


def wants_document(ask: str, tau: float = DOCUMENT_TAU) -> dict:
    score = _best_similarity(ask, DOCUMENT_EXEMPLARS)
    return {"fires": score >= tau, "score": round(score, 4), "tau": tau}


def wants_rule_application(ask: str, tau: float = RULE_TAU) -> dict:
    score = _best_similarity(ask, RULE_EXEMPLARS)
    return {"fires": score >= tau, "score": round(score, 4), "tau": tau}
