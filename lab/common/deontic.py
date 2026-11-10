"""Deontic modal classification (EXP-087, scoped): classify a sentence's
own modal verb (shall/must/may/should/can/will) into an explicit deontic
operator (obligation/permission/prohibition), checked structurally
against spaCy's negation attachment -- not lab.common.textutil.modals()'s
current "preserve this word unchanged" treatment, which finds the word
but never says what it MEANS.

Empirically verified first (not assumed from a textbook rule): a modal
("shall"/"must"/"may"/"should") surfaces as dep_=="aux" attached to the
sentence's own main VERB; a following "not" is a SIBLING "neg" child of
that SAME main verb, never a child of the modal token itself ("shall
NOT disclose" -> shall:aux and not:neg are both children of "disclose").
Negation is therefore checked on the modal's own HEAD, not on the modal
token.

Explicitly out of scope, per this todo's own stated uncertainty (no
confirmed openly-released pretrained Flint-role model, and the largest/
least-scoped of the four related todos): the full Flint framework's
Actor/Activation-Condition/Act/Object role extraction. This module only
classifies the modal's own deontic polarity, nothing about WHO the
actor is or WHAT act it governs -- lab.common.rules.extract_fact_triple/
parse_conditional_rule already extract subject/verb/object separately,
unchanged by this module.
"""

from __future__ import annotations

from lab.common.rules import _parser

# A modal's own "base" deontic reading when NOT negated. "should" is
# genuinely weaker than "shall"/"must" (an advisory, not a strict
# obligation) but mapped to the same bucket here -- a real simplification,
# named honestly in EXP-087's own scale_down, not hidden.
DEONTIC_TABLE: dict[str, str] = {
    "shall": "obligation",
    "must": "obligation",
    "will": "obligation",
    "should": "obligation",
    "may": "permission",
    "can": "permission",
}

# Negating either an obligation ("shall not") or a permission ("may not")
# produces a PROHIBITION in both cases -- "may not disclose" means
# disclosure is forbidden, not merely "not permitted but not forbidden
# either"; this collapse is deliberate, not an oversight.
_NEGATED_OPERATOR = "prohibition"


def _is_reported_question(verb_token) -> bool:
    """True if `verb_token` heads a "whether"/"if"-marked clausal
    complement -- "studying WHETHER the company should expand", "debated
    IF the project should proceed" -- a reported/hypothetical question
    embedded under some other verb, never the sentence's own direct
    assertion. Purely structural (a `mark` child lemma "whether"/"if" on
    `verb_token` ITSELF, whatever `verb_token`'s own dependency relation
    to its head is -- empirically, spaCy's parser realizes this same
    embedded-question shape as `ccomp` for one governing verb ("studying
    whether...") and `advcl` for another ("debated if...") on otherwise
    structurally identical sentences, so checking `ccomp` alone silently
    missed the second; both are accepted here, not just the one first
    found): no closed list of "reporting verbs" (study/wonder/debate/
    investigate/...) to maintain, so a verb not anticipated here is still
    caught correctly -- the fix generalizes past this project's own found
    example (HANDOFF.md, "the research team ... studying whether the
    company SHOULD expand") rather than patching only it.

    An ordinary "that"-complement directive ("the board decided THAT
    employees must report concerns") is unaffected: its `mark` is
    "that", not "whether"/"if". A real conditional directive ("IF a
    claim is filed within 30 days, the vendor must respond") is also
    unaffected: there, "if" marks the separate condition clause's own
    verb ("filed"), never a child of the modal's governing verb
    ("respond") itself -- only a "whether"/"if" sitting on the SAME verb
    the modal attaches to counts.
    """
    return verb_token.dep_ in ("ccomp", "advcl") and any(
        c.dep_ == "mark" and c.lemma_.lower() in ("whether", "if") for c in verb_token.children
    )


def classify_deontic(sentence: str) -> dict:
    """The first recognized modal's own deontic operator, or None if no
    modal from DEONTIC_TABLE is present. A modal embedded in a reported
    question (`_is_reported_question`) is skipped, not returned as a
    real directive -- the loop continues to the next modal rather than
    giving up on the whole sentence, so a second, genuine modal
    elsewhere in the same sentence is still caught. Returns the modal
    token's own text/lemma, whether its governing verb is negated, and
    the resulting operator -- never a silent default when nothing
    matches.
    """
    doc = _parser()(sentence)
    for tok in doc:
        if tok.dep_ == "aux" and tok.lemma_.lower() in DEONTIC_TABLE:
            if _is_reported_question(tok.head):
                continue
            negated = any(child.dep_ == "neg" for child in tok.head.children)
            operator = _NEGATED_OPERATOR if negated else DEONTIC_TABLE[tok.lemma_.lower()]
            return {"modal": tok.text, "lemma": tok.lemma_.lower(), "negated": negated, "operator": operator, "governing_verb": tok.head.lemma_.lower()}
    return {"modal": None, "lemma": None, "negated": False, "operator": None, "governing_verb": None}
