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
   already a project dependency -- lab/common/real_models.ner_pipeline).
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

from lab.common.calc import compare_numbers, sum_amounts

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
    # side of the number.
    r"(?P<threshold>[a-z]*\s*[\d,]+(?:\.\d+)?\s*[a-z%]*)\s*,\s*(?P<consequence>.+?)\.?\s*$",
    re.I,
)


def _parser():
    from lab.common.real_models import ner_pipeline

    return ner_pipeline()


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


def extract_fact_triple(text: str) -> dict | None:
    """Subject / verb lemma / object for a simple factual sentence, via dependency parse."""
    text = text.strip()
    doc = _parser()(text)
    root = next((t for t in doc if t.dep_ == "ROOT" and t.pos_ in ("VERB", "AUX")), None)
    if root is None or root.pos_ != "VERB":
        return None
    subject = next((t for t in root.children if t.dep_ in ("nsubj", "nsubjpass")), None)
    obj = next((t for t in root.children if t.dep_ in ("dobj", "pobj", "attr", "dative")), None)
    return {
        "raw": text,
        "subject": subject.text if subject is not None else None,
        "verb_lemma": root.lemma_.lower(),
        "object": obj.text if obj is not None else None,
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


def sum_amounts_for_subject(passages: list[dict], amount_re) -> dict:
    """Sum every amount span found across a subject's own passages (lab.common.calc.sum_amounts),
    recording which passage each amount came from so the total stays citable, not just a number.
    """
    spans = []
    sources = []
    for passage in passages:
        for found in amount_re.findall(passage.get("text", "")):
            spans.append(found)
            sources.append(passage.get("id"))
    result = sum_amounts(spans)
    result["sources"] = sources
    return result


def apply_rule(rule: dict, fact: dict) -> dict:
    """The one comparison this module makes: do the rule's and the fact's verb lemmas match.

    Exact: catches "murders"/"murdered" (same lemma) but not "unlawfully took
    her life" (different lemma, same meaning). Fast, no model, no network --
    the right default when the fact is phrased close to the rule. See
    `semantic_apply_rule` for the paraphrase-robust alternative, which costs
    a real NLI call.
    """
    matched = rule["trigger_lemma"] == fact["verb_lemma"]
    return {
        "matched": matched,
        "trigger_lemma": rule["trigger_lemma"],
        "fact_verb_lemma": fact["verb_lemma"],
        "consequence": rule["consequence"] if matched else None,
    }


def semantic_apply_rule(rule: dict, fact_text: str, tau: float = 0.75) -> dict:
    """Does the fact satisfy the rule's condition, by meaning rather than by shared verb.

    `apply_rule`'s lemma check is exact-match brittle: a fact phrased without
    the rule's trigger verb at all ("Arjun unlawfully took Neha's life" for a
    rule triggered on "murders") fails it even though the fact plainly
    satisfies the rule. This checks one-directional entailment instead --
    does the specific fact entail that the rule's general condition holds --
    using the real DeBERTa-v3 MNLI checkpoint (lab.common.real_encoders,
    already measured in EXP-031/041/056), not lexical overlap. Still one
    bounded judgment (one NLI call, one threshold), just a more capable one
    than lemma equality. The direction matters: the condition does not
    entail the fact (a general rule doesn't imply any one specific
    instance), only the fact entails the condition is satisfied.
    """
    from lab.common.real_encoders import real_nli

    probs = real_nli(fact_text, rule["condition_text"])
    matched = probs["entail"] >= tau and probs["contradict"] < 0.2
    return {
        "matched": matched,
        "condition_text": rule["condition_text"],
        "fact_text": fact_text,
        "nli": probs,
        "consequence": rule["consequence"] if matched else None,
    }


def answer_rule_question(ask: str, passages: list[dict]) -> dict:
    """Find a rule and a fact among the given passages, apply the rule, answer the ask.

    `passages`: [{"id": ..., "text": ...}, ...], the same shape every other
    retrieval-facing function in this repo uses, so citations carry through.
    Abstains (decision "inconclusive") if no rule sentence, no fact sentence
    with a concrete (non-generic) subject, or no verb match is found --
    never guesses a yes/no from the ask's wording alone.
    """
    rule = rule_passage = None
    fact = fact_passage = None
    for passage in passages:
        text = passage.get("text", "")
        if rule is None:
            candidate = parse_conditional_rule(text)
            if candidate:
                rule, rule_passage = candidate, passage
                continue
        if fact is None:
            candidate = extract_fact_triple(text)
            if candidate and candidate["subject"] and candidate["subject"].lower() not in {
                "it", "someone", "anyone", "somebody", "something",
            }:
                fact, fact_passage = candidate, passage
    if rule is None or fact is None:
        return {
            "decision": "inconclusive",
            "reason": "missing_rule" if rule is None else "missing_fact",
            "rule": rule,
            "fact": fact,
            "text": "Insufficient evidence.",
        }
    result = apply_rule(rule, fact)
    if not result["matched"]:
        return {
            "decision": "inconclusive",
            "reason": "no_verb_match",
            "rule": rule,
            "fact": fact,
            "applied": result,
            "text": "Insufficient evidence.",
        }
    rule_cite = rule_passage.get("id", "rule")
    fact_cite = fact_passage.get("id", "fact")
    text = (
        f"{fact['raw']} [{fact_cite}] This matches the rule's trigger ({result['trigger_lemma']}): "
        f"{rule['raw']} [{rule_cite}] Therefore, {rule['consequence']}."
    )
    return {
        "decision": "supported",
        "reason": "verb_match",
        "rule": rule,
        "fact": fact,
        "applied": result,
        "text": text,
        "citations": [rule_cite, fact_cite],
    }
