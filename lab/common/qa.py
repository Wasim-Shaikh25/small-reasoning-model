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
AMOUNT_RE = re.compile(
    r"\b(?:INR|USD|Rs\.?|\$|€|£)\s?\d[\d,]*(?:\.\d+)?\b"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:days|day|months|percent|%|grams|gram|minutes|minute|seconds|second|mg|tablets|times)\b"
    r"|\b\d+(?:\.\d+)?\s*C\b",
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
