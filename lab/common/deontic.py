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


def classify_deontic(sentence: str) -> dict:
    """The first recognized modal's own deontic operator, or None if no
    modal from DEONTIC_TABLE is present. Returns the modal token's own
    text/lemma, whether its governing verb is negated, and the resulting
    operator -- never a silent default when nothing matches.
    """
    doc = _parser()(sentence)
    for tok in doc:
        if tok.dep_ == "aux" and tok.lemma_.lower() in DEONTIC_TABLE:
            negated = any(child.dep_ == "neg" for child in tok.head.children)
            operator = _NEGATED_OPERATOR if negated else DEONTIC_TABLE[tok.lemma_.lower()]
            return {"modal": tok.text, "lemma": tok.lemma_.lower(), "negated": negated, "operator": operator, "governing_verb": tok.head.lemma_.lower()}
    return {"modal": None, "lemma": None, "negated": False, "operator": None, "governing_verb": None}
