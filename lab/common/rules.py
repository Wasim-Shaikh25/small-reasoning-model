"""Rule application: match a given conditional rule against a given fact.

This is a reasoning primitive this project didn't have until now. EXP-007's
hop chain feeds one extracted span into the next question's template
(entity A -> entity A's address); EXP-014's `conditional()` matches exactly
one hardcoded "if X, Y unless Z" sentence shape. Neither applies a general
rule ("if someone does V to anyone, consequence C") to a specific fact
("Arjun murdered Neha") and answers a question from the result -- the
classic "context gives you a rule, context gives you a fact, what follows"
pattern.

Built as AGENT.md's decomposition rule asks: one bounded judgment per step.
1. Find the rule sentence's trigger verb (via spaCy's dependency parser,
   already a project dependency -- lab/common/real_models.parser_pipeline).
2. Find the fact sentence's own verb, subject, and object the same way.
3. Compare the two verb lemmas. One equality check. Nothing more is
   "reasoned" here.
4. If they match, the rule's consequence clause is the answer, attributed
   to both the rule and the fact passage.

No model decides the outcome; spaCy's parser only extracts the verb, which
is a narrow syntactic sub-task, not a judgment call. A generative model is
never involved, per FORBIDDEN.md.

Known, named limit (the same one EXP-026 already flagged for the lexical
NLI judge): a rule with an exception ("...unless committed in self-
defense") is not parsed here. A matched trigger is reported as a match,
not screened against every qualifier a human reader would catch. This is a
scale-down, stated as one, not hidden.
"""

from __future__ import annotations

import re

from lab.common.calc import compare_numbers

RULE_RE = re.compile(
    r"^\s*if\s+(?P<subject>.+?)\s+(?P<verb_phrase>.+?),\s*(?P<consequence>.+?)\.?\s*$",
    re.I,
)

THRESHOLD_RULE_RE = re.compile(
    r"if\s+(?P<subject>.+?)'s\s+(?P<metric>.+?)\s+"
    r"(?:exceeds|is (?:greater|more) than|is over|goes over)\s+"
    # The number can be unit-prefixed ("INR 30000") or unit-suffixed ("90
    # degrees", "3 days") -- the same two shapes textutil.NUM_RE/qa.AMOUNT_RE
    # already both handle elsewhere in this repo. A rule shouldn't need a
    # new regex every time the quantity's unit happens to sit on the other
    # side of the number. The prefix class also includes the common currency
    # symbols ($/€/£), found missing (EXP-069) when a threshold phrased as
    # "exceeds $10000" failed to parse at all -- only letter prefixes like
    # "INR" were accounted for.
    r"(?P<threshold>[a-z$€£]*\s*[\d,]+(?:\.\d+)?\s*[a-z%]*)\s*,\s*(?P<consequence>.+?)\.?\s*$",
    re.I,
)


def _parser():
    from lab.common.real_models import parser_pipeline

    return parser_pipeline()


def _main_verb(doc, within: "range | None" = None):
    for token in doc:
        if within is not None and token.i not in within:
            continue
        if token.pos_ == "VERB" or (token.pos_ == "AUX" and token.dep_ == "ROOT"):
            if token.dep_ in ("ROOT", "advcl", "ccomp", "conj"):
                return token
    for token in doc:
        if within is not None and token.i not in within:
            continue
        if token.pos_ == "VERB":
            return token
    return None


def parse_conditional_rule(text: str) -> dict | None:
    """Extract a rule's trigger verb lemma and its consequence clause.

    Supports one sentence shape: "If <subject>, <verb phrase>, <consequence>."
    Returns None if the sentence isn't an if-rule at all -- that is a
    structural mismatch, not a failed judgment call.
    """
    text = text.strip()
    match = RULE_RE.match(text)
    if not match:
        return None
    doc = _parser()(text)
    if_token = next((t for t in doc if t.lower_ == "if"), None)
    comma_idx = text.find(",")
    clause_end = len(text)
    if comma_idx >= 0:
        char_to_tok = {t.idx: t.i for t in doc}
        for idx in range(comma_idx, -1, -1):
            if idx in char_to_tok:
                clause_end = char_to_tok[idx]
                break
    within = range(if_token.i, clause_end) if if_token is not None else None
    verb = _main_verb(doc, within=within)
    if verb is None:
        return None
    condition_start = text.lower().find("if") + 2
    condition_end_char = comma_idx if comma_idx >= 0 else len(text)
    condition_text = text[condition_start:condition_end_char].strip()
    return {
        "raw": text,
        "subject_placeholder": match.group("subject").strip(),
        "trigger_lemma": verb.lemma_.lower(),
        "condition_text": condition_text,
        "consequence": match.group("consequence").strip().rstrip("."),
    }


def _span_text(token) -> str:
    """The full noun phrase a token heads ("14 MG Road", not just "Road"),
    reconstructed from its dependency subtree in sentence order -- not the
    single head token's own text. Found needed (lab.common.working_memory,
    EXP-053): a head-token-only object collapses "14 MG Road" and "22 Lake
    View Road" to the identical string "Road", making two genuinely
    different facts indistinguishable. Safe to widen here rather than add
    a second extractor: no existing caller (lab.common.brain's apply_rule,
    EXP-057/059/061) compares `subject`/`object` by exact value -- only
    `verb_lemma` ever gets matched -- so a fuller, more informative span
    changes nothing any of them actually check.
    """
    return " ".join(t.text for t in sorted(token.subtree, key=lambda t: t.i))


def extract_fact_triple(text: str) -> dict | None:
    """Subject / verb lemma / object for a simple factual sentence, via dependency parse."""
    text = text.strip()
    doc = _parser()(text)
    root = next((t for t in doc if t.dep_ == "ROOT" and t.pos_ in ("VERB", "AUX")), None)
    if root is None or root.pos_ != "VERB":
        return None
    subject = next((t for t in root.children if t.dep_ in ("nsubj", "nsubjpass")), None)
    obj = next((t for t in root.children if t.dep_ in ("dobj", "pobj", "attr", "dative")), None)
    if obj is None:
        # A prepositional-phrase object ("lives AT X", "works AT Y",
        # "registered IN Z") is the pobj's own object, not a direct child
        # of the root verb -- it's one level deeper, under the "prep"
        # relation. Found missing (lab.common.working_memory, EXP-053):
        # every address/employer-style sentence in this project's own
        # fixtures is phrased this way, and the direct-object-only version
        # silently returned no object for all of them. Only a fallback,
        # checked after every direct-object shape above, so a sentence
        # that already had a real dobj/attr/dative is completely
        # unaffected -- this never overrides an object the old behavior
        # already found.
        prep = next((t for t in root.children if t.dep_ == "prep"), None)
        if prep is not None:
            obj = next((t for t in prep.children if t.dep_ == "pobj"), None)
    return {
        "raw": text,
        "subject": _span_text(subject) if subject is not None else None,
        "verb_lemma": root.lemma_.lower(),
        "object": _span_text(obj) if obj is not None else None,
    }


def parse_threshold_rule(text: str) -> dict | None:
    """A second rule shape: 'if <subject>'s <metric> exceeds <threshold>, <consequence>.'

    Same principle as `parse_conditional_rule`, a different trigger: instead
    of a verb match, the trigger is a numeric comparison (lab.common.calc.
    compare_numbers), which this project already has and already uses for
    date/amount arithmetic (EXP-007, EXP-014). A company policy phrased this
    way ("if a contractor's total billed amount exceeds INR 30000...") is a
    threshold rule, not a verb-trigger rule, and needs its own parser rather
    than forcing it through parse_conditional_rule's shape.
    """
    match = THRESHOLD_RULE_RE.search(text.strip())
    if not match:
        return None
    return {
        "raw": text.strip(),
        "subject_placeholder": match.group("subject").strip(),
        "metric": match.group("metric").strip(),
        "threshold": match.group("threshold").strip(),
        "consequence": match.group("consequence").strip().rstrip("."),
    }


def apply_threshold_rule(rule: dict, computed_value: float) -> dict:
    """The one comparison this rule shape makes: is the computed value over the threshold."""
    comparison = compare_numbers(str(computed_value), rule["threshold"])
    matched = bool(comparison.get("ok")) and comparison["relation"] == "greater"
    return {
        "matched": matched,
        "computed_value": computed_value,
        "threshold": rule["threshold"],
        "comparison": comparison,
        "consequence": rule["consequence"] if matched else None,
    }


def apply_rule(rule: dict, fact: dict) -> dict:
    """The one comparison this module makes: do the rule's and the fact's verb lemmas match.

    Exact: catches "murders"/"murdered" (same lemma) but not "unlawfully took
    her life" (different lemma, same meaning). Fast, no model, no network --
    the right default when the fact is phrased close to the rule. See
    `lab.tests.support.semantic_apply_rule` for the paraphrase-robust
    alternative, which costs a real NLI call.
    """
    matched = rule["trigger_lemma"] == fact["verb_lemma"]
    return {
        "matched": matched,
        "trigger_lemma": rule["trigger_lemma"],
        "fact_verb_lemma": fact["verb_lemma"],
        "consequence": rule["consequence"] if matched else None,
    }


# semantic_apply_rule (paraphrase-robust NLI matching) and
# answer_rule_question (a standalone find-rule+find-fact+apply+render demo
# pipeline) moved to lab.tests.support on 2026-11-12 -- lab.common.brain's
# rule_application stage calls apply_rule (exact lemma match) directly and
# has its own dispatch/citation logic; neither function here was ever
# called from lab.common itself.
