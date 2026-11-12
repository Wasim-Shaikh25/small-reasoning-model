"""Deterministic ask-relevance scoring: does a candidate text actually address the ask?

This is the check the fidelity gate was missing: lab.tests.support.fidelity and
lab.common.real_rewriter.fidelity_gate confirm a rewrite didn't drop or invent a
fact relative to its *source findings*, but nothing confirmed the output still
answers the *ask* that produced those findings in the first place. A small model
can stay perfectly faithful to its source text and still wander off-topic, or
collapse to something technically "safe" (EXP-054's citation-only collapse) that
no longer serves the ask at all.

Classical, no model: content-token coverage of the ask's key terms in the
candidate text, the same style of judge lab/common/nli.py and lab/common/qa.py
already use. Per AGENT.md's decomposition rule, this is one bounded judgment --
does this text contain the ask's key terms -- not an attempt at deep semantic
matching.
"""

from __future__ import annotations

from lab.common.textutil import content_tokens, coverage


def ask_relevance(ask: str, text: str, tau: float = 0.2) -> dict:
    """Coverage of the ask's content tokens in the candidate text.

    tau=0.2 is deliberately low: this check exists to catch gross drift (an
    empty or off-topic rewrite), not to second-guess a faithful paraphrase's
    wording. The fidelity gate already enforces word-for-word preservation of
    numbers, modals, and citations; this check only adds "and it still has
    something to do with what was asked."
    """
    ask_tokens = content_tokens(ask)
    text_tokens = content_tokens(text)
    if not ask_tokens:
        return {"coverage": None, "relevant": True, "ask_tokens": 0}
    cov = coverage(ask_tokens, text_tokens)
    return {"coverage": round(cov, 4), "relevant": cov >= tau, "ask_tokens": len(ask_tokens)}
