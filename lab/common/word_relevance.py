"""Per-word relevance and grammaticality scoring (EXP-049): the first
stage of the word-by-word relevance cascade AGENT.md names (chunk the
prompt, then check every nearby word's relevance and grammar before
deciding how to use the sentence) -- scoring individual content words in
a candidate sentence, rather than lab.common.relevance.ask_relevance's
existing whole-sentence coverage score.

Two independent, bounded judgments per AGENT.md's decomposition rule,
neither a generative model:
  - Relevance: does this content word's surface form fuzzy-match one of
    the ask's own content words -- the same lexical, prefix-tolerant
    matching lab.common.textutil._token_close/coverage already use for
    ask_relevance, just scored per word instead of as one aggregate
    number.
  - Grammaticality: does the sentence have a complete clause (a ROOT
    verb with its own subject), via spaCy's dependency parse -- not a
    fragment like "of the processing" or "to protect the vital
    interests" lifted out of context, which a naive sentence splitter
    can produce at a clause boundary.
"""

from __future__ import annotations

from lab.common.rules import _parser
from lab.common.textutil import _token_close, content_tokens


def score_words(ask: str, sentence: str) -> list[dict]:
    """Every content word in `sentence`, marked relevant if it fuzzy-
    matches one of the ask's own content words. Returns one entry per
    content word, in order -- never a single aggregate score, so a
    caller can see exactly which words carried the match and which
    didn't.
    """
    ask_words = content_tokens(ask)
    results = []
    for word in content_tokens(sentence):
        relevant = any(_token_close(word, ask_word) for ask_word in ask_words)
        results.append({"word": word, "relevant": relevant})
    return results


def grammatical_check(sentence: str) -> dict:
    """Is this a complete clause -- a ROOT verb/aux with its own subject
    -- not a bare fragment. Checked structurally (spaCy's dependency
    parse), not by a length or punctuation heuristic: a short complete
    sentence ("He ran.") must pass, and a long fragment ("of the
    establishment, exercise or defence of legal claims") must fail.
    """
    doc = _parser()(sentence)
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root is None or root.pos_ not in ("VERB", "AUX"):
        return {"well_formed": False, "reason": "no_root_verb"}
    has_subject = any(t.dep_ in ("nsubj", "nsubjpass", "expl") for t in root.children)
    if not has_subject:
        return {"well_formed": False, "reason": "no_subject"}
    return {"well_formed": True, "reason": None}


def sentence_admission(ask: str, sentence: str, min_relevant_words: int = 1) -> dict:
    """Combines both checks into the one decision this stage exists to
    make: should this sentence be allowed into the shortlist that feeds
    extraction. Both conditions are required -- a grammatically complete
    but off-topic sentence, or an on-topic sentence that's really a
    fragment lifted out of context, are each a real rejection reason, not
    interchangeable with the other.
    """
    grammar = grammatical_check(sentence)
    words = score_words(ask, sentence)
    relevant_count = sum(1 for w in words if w["relevant"])
    admitted = grammar["well_formed"] and relevant_count >= min_relevant_words
    return {"admitted": admitted, "grammar": grammar, "words": words, "relevant_count": relevant_count}
