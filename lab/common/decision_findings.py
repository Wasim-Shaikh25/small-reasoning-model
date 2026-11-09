"""Flag decision/finding-bearing sentences in a research or organizational
document -- {statement, finding_type, citation} shape, same as
notes_to_findings.py, zero generative-model calls.

Built and tested (2026-11-09, one of four "big experiment" runs) against a
synthetic ~750-word decision memo: 45 sentences, 14 flagged. Checked by
hand against the source, not just trusted from a count -- precision ~93%
(13/14 correct), recall ~93% (13/14 of the memo's real decisions caught).

Combines two already-validated, structurally-detected signals, never a new
one: `deontic.classify_deontic` (modal obligation/permission/prohibition,
EXP-087, previously built but never wired into anything) catches
"shall"/"must"/"may" directives; `DECISION_VERBS` below catches non-modal
decision language ("the committee decided...", "the board approved...")
via the sentence's own structural ROOT verb lemma (spaCy dependency parse,
same grounding as `connectives.py`/`deontic.py` -- never a substring match,
which would also fire on "the decision process was reviewed").

Two confirmed, unfixed failure modes, found by hand-checking the output
against the source rather than assumed away:
  1. A reported/embedded modal reads as a real directive. "The research
     team spent six weeks studying whether the company SHOULD expand..."
     is a description of a research QUESTION, not an actual obligation --
     `classify_deontic` only checks the modal's own negation, not whether
     it sits inside a reported-question clause ("studying whether X"),
     so this is wrongly flagged `obligation`. One false positive out of
     14 on the test fixture.
  2. A non-modal, non-DECISION_VERBS passive decision is missed entirely.
     "A follow-up review is scheduled for the end of the second
     quarter..." -- ROOT verb "schedule" isn't in the closed table, and
     there's no modal to catch it either. One false negative out of the
     memo's real decisions.
  3. (Non-blocking, an ordering artifact, not a detection failure) when a
     sentence has BOTH a decision verb and an embedded modal ("The
     committee resolved that ... must be satisfied..."), `classify_deontic`
     is checked first, so the sentence is tagged `obligation` instead of
     `decision` -- still correctly flagged as a finding, just a less
     precise type label.

Neither failure mode is fixed here. This module is accurate enough to be
useful as a first-pass flagger on a document a person will still read, not
accurate enough to run unsupervised on a document nobody checks.
"""

from __future__ import annotations

from lab.common.deontic import classify_deontic
from lab.common.rules import _parser
from lab.common.textutil import sentences

DECISION_VERBS = {
    "decide", "conclude", "approve", "recommend", "resolve", "agree",
    "reject", "authorize", "determine",
}


def classify_sentence(sentence: str) -> dict:
    """{"finding_type": "obligation"|"permission"|"prohibition"|"decision"|None,
    "signal": str|None, "negated": bool}. `classify_deontic` is checked
    first (see module docstring's point 3 for why that ordering matters);
    `DECISION_VERBS` only fires when no modal matched.
    """
    deontic = classify_deontic(sentence)
    if deontic["operator"]:
        return {"finding_type": deontic["operator"], "signal": f"modal:{deontic['lemma']}", "negated": deontic["negated"]}

    doc = _parser()(sentence)
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root is not None and root.lemma_.lower() in DECISION_VERBS:
        return {"finding_type": "decision", "signal": f"root_verb:{root.lemma_.lower()}", "negated": False}

    return {"finding_type": None, "signal": None, "negated": False}


def extract_decision_findings(text: str, citation: str | None = None) -> list[dict]:
    """Splits `text` into sentences and classifies each one. Returns only
    the flagged findings, in `notes_to_findings.py`'s {finding_id,
    statement, citation} shape plus `finding_type`/`signal` -- a drop-in
    source for `assemble.py`, same as that module's own output.
    """
    findings = []
    for i, sent in enumerate(sentences(text)):
        cls = classify_sentence(sent)
        if cls["finding_type"]:
            findings.append({
                "finding_id": f"D{i + 1}",
                "statement": sent,
                "citation": citation or "SOURCE",
                "finding_type": cls["finding_type"],
                "signal": cls["signal"],
            })
    return findings
