"""Extractive QA by span selection inside retrieved sentences. Two lexical extractors."""

from __future__ import annotations

import re

from lab.common.textutil import (
    DATE_RE,
    content_tokens,
    coverage,
    jaccard,
    normalize,
    numbers,
    sentences,
)

PERSON_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Shri|Smt)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
    r"|\b[A-Z][a-z]+\s+[A-Z][a-z]+\b"
    r"|\b[A-Z]\.\s*[A-Z][a-z]+\b"
)
# Sibling copy of lab.common.entities._AMOUNT_UNIT_STOPWORDS -- not
# imported from there to avoid a circular import (entities.py already
# imports from this module). A closed, finite set of English function
# words, not a growing domain-vocabulary list.
_AMOUNT_UNIT_STOPWORDS = (
    r"(?:he|she|it|we|us|you|they|is|was|are|am|be|to|of|in|on|at|by|or|and"
    r"|the|a|an|as|if|so|do|did|has|had|can|may|not|no|nor|but|yet|for|up|out|off)"
)

AMOUNT_RE = re.compile(
    # Same bugs lab.common.entities.AMOUNT_RE had until EXP-069/070, fixed
    # the same way here: (1) a literal \b right before a symbol currency
    # ($/€/£) can never match -- \b needs a word/non-word transition, and a
    # symbol preceded by whitespace is non-word on both sides -- so symbol
    # currencies get their own branch with no leading \b. (2) the old
    # enumerated unit list (days/months/grams/mg/tablets/...) was ad hoc
    # per-scenario accretion; replaced with a capitalization-based
    # distinction (unit vs. street-name word) plus a function-word
    # exclusion (an ordinary short word like "he" can otherwise look like a
    # unit right after a number) -- see lab.common.entities.AMOUNT_RE for
    # the full rationale, identical here. (?-i: ...) keeps the two
    # capitalization lookaheads case-sensitive despite the outer re.I.
    # (?:\d[\d,]*\d|\d), not \d[\d,]*: a comma inside the number must be
    # followed by another digit (a real thousands separator), never an
    # ordinary trailing punctuation comma -- see lab.common.entities.AMOUNT_RE
    # for the "TC-19, taken" false positive this fixes.
    r"\b(?:INR|USD|Rs\.?)\s?(?:\d[\d,]*\d|\d)(?:\.\d+)?\b"
    r"|[$€£]\s?(?:\d[\d,]*\d|\d)(?:\.\d+)?\b"
    r"|\b(?:\d[\d,]*\d|\d)(?:\.\d+)?\s?(?:percent|%)\b"
    r"|\b(?:\d[\d,]*\d|\d)(?:\.\d+)?\s?(?!" + _AMOUNT_UNIT_STOPWORDS + r"\b)(?-i:(?![A-Z][a-z]+\b))[A-Za-z]{1,7}\b(?-i:(?!\s+[A-Z]))",
    re.I,
)


def _best_sentence(question: str, passage: str, mode: str) -> tuple[str, float]:
    q = content_tokens(question)
    best, best_score = "", 0.0
    for sent in sentences(passage):
        s = content_tokens(sent)
        if mode == "bigram":
            qt, st = q, s
            q_b = set(zip(qt, qt[1:]))
            s_b = set(zip(st, st[1:]))
            score = (len(q_b & s_b) / len(q_b)) if q_b else coverage(q, s)
            score = 0.5 * score + 0.5 * coverage(q, s)
        else:
            score = coverage(q, s)
            score = 0.75 * score + 0.25 * jaccard(q, s)
        if score > best_score:
            best, best_score = sent, score
    return best, best_score


def _span_from_sentence(question: str, sentence: str) -> str | None:
    if not sentence:
        return None
    low = question.lower()
    if low.startswith("when") or "what date" in low or "which date" in low:
        found = DATE_RE.findall(sentence)
        return found[0] if found else None
    if low.startswith("who") or low.startswith("whose"):
        found = PERSON_RE.findall(sentence)
        # PERSON_RE has no groups; findall returns strings.
        if found:
            # Prefer the name nearest a parenthetical role if present.
            role = re.search(r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+\(the\s+[A-Z][a-z]+\)", sentence)
            if role:
                return role.group(1)
            return found[0]
        return None
    if any(p in low for p in ("how many", "how much", "what amount", "how long", "what is the amount")):
        found = AMOUNT_RE.findall(sentence) or numbers(sentence)
        return found[0] if found else None
    means = re.search(r"\b(?:is|means|equals|:)\s+([^.;]+)", sentence, re.I)
    focus = re.search(r"what(?:'s| is)(?: the)? (.+?)\??$", low)
    if focus and means:
        return means.group(1).strip()
    if means and coverage(content_tokens(question), content_tokens(sentence)) >= 0.34:
        return means.group(1).strip()
    return sentence


def answer_question(
    question: str,
    passages: list[dict],
    *,
    tau: float = 0.34,
    mode: str = "unigram",
) -> dict:
    best = {
        "span": None,
        "score": 0.0,
        "no_answer": 1.0,
        "passage_id": None,
        "sentence": None,
        "abstained": True,
    }
    for passage in passages:
        sent, score = _best_sentence(question, passage.get("text", ""), mode)
        if score > best["score"]:
            span = _span_from_sentence(question, sent)
            best = {
                "span": span,
                "score": round(score, 4),
                "no_answer": round(1.0 - score, 4),
                "passage_id": passage.get("id") or passage.get("chunk_id"),
                "sentence": sent,
                "abstained": span is None or score < tau,
            }
    if best["span"] is None or best["score"] < tau:
        best["abstained"] = True
        best["span"] = None if best["score"] < tau else best["span"]
        if best["score"] < tau:
            best["span"] = None
    return best


def spans_overlap(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    na, nb = normalize(a), normalize(b)
    if na == nb or na in nb or nb in na:
        return True
    return len(set(na.split()) & set(nb.split())) >= max(1, min(len(na.split()), len(nb.split())) // 2)


def answer_with_agreement(question: str, passages: list[dict], tau: float = 0.34) -> dict:
    first = answer_question(question, passages, tau=tau, mode="unigram")
    second = answer_question(question, passages, tau=tau, mode="bigram")
    first["second_span"] = second.get("span")
    first["second_model_agrees"] = spans_overlap(first.get("span"), second.get("span"))
    return first


def answer_with_real_qa(question: str, passages: list[dict], score_floor: float = 0.1) -> dict:
    """Same return contract as answer_with_agreement -- {"span", "score",
    "no_answer", "passage_id", "sentence", "abstained", "second_span",
    "second_model_agrees"} -- but the span and score come from the real
    deepset/deberta-v3-base-squad2 checkpoint (lab.common.real_encoders.
    real_qa), one call per passage, best-scoring non-no-answer result
    wins, rather than this module's classical lexical extractors.

    Opt-in only (lab.common.brain.reason(use_real_qa=True)); flagged by
    the 2026-11-03 reasoning-layer audit (AUDIT.md, Top Finding #1): this
    project has repeatedly measured real_qa (EXP-030/080) but no live
    caller ever actually used it until this function existed. `tau`'s
    existing calibrated values (0.1/0.34, measured for the classical
    lexical score distribution) don't transfer to a real QA confidence
    score, which runs on a different scale -- `score_floor` is this
    function's OWN first measured value, not swept across fixtures, same
    caveat every other first-measured threshold in this repo carries.
    `second_span`/`second_model_agrees` are populated from the classical
    bigram extractor (the cheapest available second opinion), not a
    second real-model call -- this function adds one real-model call per
    passage, not two.
    """
    from lab.common.real_encoders import real_qa

    best = {"span": None, "score": 0.0, "no_answer": True, "passage_id": None, "sentence": None, "abstained": True}
    for passage in passages:
        text = passage.get("text", "") or ""
        if not text:
            continue
        result = real_qa(question, text)
        if result["no_answer"] or not result["answer"]:
            continue
        if result["score"] > best["score"]:
            best = {
                "span": result["answer"],
                "score": round(result["score"], 4),
                "no_answer": False,
                "passage_id": passage.get("id") or passage.get("chunk_id"),
                "sentence": result["answer"],
                "abstained": result["score"] < score_floor,
            }
    if best["score"] < score_floor:
        best["span"] = None
        best["abstained"] = True
    second = answer_question(question, passages, tau=0.34, mode="bigram")
    best["second_span"] = second.get("span")
    best["second_model_agrees"] = spans_overlap(best.get("span"), second.get("span"))
    return best
