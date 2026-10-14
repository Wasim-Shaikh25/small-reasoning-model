"""Provenance tags: evidence, background, inference. Context wins over background."""

from __future__ import annotations

from lab.common.textutil import span_in_passage

# Logged common-sense priors. They are never allowed to support a factual claim alone.
BACKGROUND_FACTS = {
    "capital of france": "Paris",
    "sprint length": "14 days",
    "water boiling point": "100 C",
    "number of continents": "7",
}


def tag_statement(statement: str, evidence_text: str, span: str | None, kind: str) -> dict:
    if kind == "inference":
        return {"statement": statement, "tag": "inference", "kept": True, "reason": "stated_step"}
    if span and span_in_passage(span, evidence_text):
        return {"statement": statement, "tag": "evidence", "kept": True, "reason": "quoted_span"}
    return {
        "statement": statement,
        "tag": "background",
        "kept": False,
        "reason": "not established in the provided material",
    }


def answer_from_context_or_abstain(question_key: str, context_span: str | None, evidence_text: str) -> dict:
    background = BACKGROUND_FACTS.get(question_key)
    if context_span and span_in_passage(context_span, evidence_text):
        return {
            "answer": context_span,
            "tag": "evidence",
            "background_ignored": background,
            "abstained": False,
        }
    return {
        "answer": None,
        "tag": "background",
        "background_available": background,
        "abstained": True,
        "reason": "not established in the provided material",
    }
