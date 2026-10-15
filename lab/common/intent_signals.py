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

# A compound ask ("Who is X, and where do they live? What's their total,
# and does policy require approval?") scored as one whole string dilutes
# whichever clause actually carries the signal -- the same problem EXP-056
# already found for ask-relevance, resurfacing here (EXP-069). Splitting on
# sentence-ending punctuation and the conjunction "and" and scoring each
# clause separately, then taking the best clause's score, keeps one
# unrelated clause from dragging down a real match in another.
_CLAUSE_SPLIT_RE = re.compile(r"[?.;]|\band\b", re.I)


def _clauses(ask: str) -> list[str]:
    parts = [p.strip() for p in _CLAUSE_SPLIT_RE.split(ask) if p.strip()]
    return parts or [ask]


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

IDENTITY_TAU = 0.5971
TOTAL_TAU = 0.6084


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
