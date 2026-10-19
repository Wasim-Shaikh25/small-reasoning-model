"""Neighbor-sentence coherence check for page-wise assembly (EXP-050):
before a sentence is placed into an outline leaf, does it read coherently
next to its immediate neighbor -- two independent, bounded signals,
neither a generative model:

  - Semantic continuity: bge cosine similarity between consecutive
    sentences (lab.common.real_encoders.bge_similarity, already loaded
    for EXP-040/042) -- catches a genuine topic jump a shared word
    wouldn't.
  - Discourse-connective structure: does the SECOND sentence open with a
    structurally-detected discourse adverbial (however/therefore/
    moreover/nevertheless/in addition -- lab.common.connectives'
    DISCOURSE_ADVERBIAL_TABLE, EXP-050's own addition to that module) --
    found via spaCy's dependency parse, never a literal keyword scan,
    the same standing rule lab.common.connectives itself was built
    under. A connective's presence does not by itself confirm
    coherence (a misused "therefore" can still be a non-sequitur), so
    this is reported as a separate signal, not folded into one score.
"""

from __future__ import annotations

from lab.common.connectives import find_connectives
from lab.common.real_encoders import bge_similarity


def neighbor_coherence(first: str, second: str) -> dict:
    """One bounded judgment on a pair of consecutive sentences: how
    semantically similar are they, and does the second one open with a
    detected discourse connective. Returns both signals raw -- never
    collapsed into a single pass/fail -- so a caller can decide its own
    threshold and whether a present connective should raise or lower its
    bar for the similarity score.
    """
    similarity = bge_similarity(first, second)
    connectives = find_connectives(second)
    opening_connective = next((m for m in connectives if m.operator is not None), None)
    return {
        "similarity": round(similarity, 4),
        "opening_connective": opening_connective.phrase if opening_connective else None,
        "opening_connective_operator": opening_connective.operator if opening_connective else None,
    }


COHERENCE_TAU = 0.65
# Measured directly (lab/exp_050_neighbor_coherence/run.py): bge never
# scores an unrelated sentence pair near 0 -- "The data subject has
# given explicit consent..." vs an unrelated weather sentence still
# scored 0.5005, the same property lab.common.brain's own
# MIN_SEMANTIC_MARGIN docstring already warns about ("embeddings never
# score unrelated text near zero the way TF-IDF does"). A genuinely
# coherent pair on the same fixture scored 0.7901. tau=0.3 (this
# function's first version) sat BELOW the unrelated score, so it never
# flagged anything real -- found and fixed in the same exploration that
# introduced it, not a separately discovered bug.


def sequence_coherence(sentences: list[str], tau: float = COHERENCE_TAU) -> list[dict]:
    """Every consecutive pair in `sentences`, flagged when similarity
    falls below `tau` AND the second sentence carries no discourse
    connective at all -- a real topic jump with nothing signaling the
    reader should expect one. A low-similarity pair that DOES open with
    a connective ("However, ...") is not flagged: the connective is
    itself the signal that a shift is coming, which is exactly the case
    a bare similarity-floor check would wrongly punish.
    """
    flags = []
    for i in range(len(sentences) - 1):
        result = neighbor_coherence(sentences[i], sentences[i + 1])
        flagged = result["similarity"] < tau and result["opening_connective"] is None
        flags.append({"index": i, "first": sentences[i], "second": sentences[i + 1], **result, "flagged": flagged})
    return flags
