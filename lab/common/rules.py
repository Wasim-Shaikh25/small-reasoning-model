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

RULE_RE = re.compile(
    r"^\s*if\s+(?P<subject>.+?)\s+(?P<verb_phrase>.+?),\s*(?P<consequence>.+?)\.?\s*$",
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
    return {
        "raw": text,
        "subject_placeholder": match.group("subject").strip(),
        "trigger_lemma": verb.lemma_.lower(),
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


def apply_rule(rule: dict, fact: dict) -> dict:
    """The one comparison this module makes: do the rule's and the fact's verb lemmas match."""
    matched = rule["trigger_lemma"] == fact["verb_lemma"]
    return {
        "matched": matched,
        "trigger_lemma": rule["trigger_lemma"],
        "fact_verb_lemma": fact["verb_lemma"],
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
