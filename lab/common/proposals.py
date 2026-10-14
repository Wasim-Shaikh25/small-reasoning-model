"""Grounding filter for proposed queries. Proposals are never evidence.

This module does not call a generator. It only accepts or drops candidate strings.
"""

from __future__ import annotations

import re

from lab.common.textutil import content_tokens, numbers

GENERIC = {
    "what", "when", "where", "who", "which", "how", "is", "are", "the", "of",
    "a", "an", "and", "or", "to", "in", "on", "for", "notice", "period",
    "address", "date", "amount", "party", "clause", "defined", "term",
    "compare", "difference", "timeline", "value", "stated", "document",
}
NAME_RE = re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b")
DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},?\s+\d{4})\b",
    re.I,
)


def _source_terms(ask: str, context: str, memory_terms: list[str]) -> set[str]:
    terms = set(content_tokens(ask)) | set(content_tokens(context)) | set(memory_terms)
    terms |= GENERIC
    return terms


def grounding_filter(proposal: str, ask: str, context: str, memory_terms: list[str] | None = None) -> dict:
    memory_terms = memory_terms or []
    text = (proposal or "").strip()
    if not text or len(text) > 300 or "\n\n" in text:
        return {"keep": False, "reason": "malformed"}
    sources = _source_terms(ask, context, memory_terms)
    source_blob = f"{ask}\n{context}\n{' '.join(memory_terms)}"
    new_numbers = [n for n in numbers(text) if n not in source_blob]
    new_dates = [d for d in DATE_RE.findall(text) if d.lower() not in source_blob.lower()]
    new_names = [n for n in NAME_RE.findall(text) if n.lower() not in source_blob.lower()]
    unknown_terms = [t for t in content_tokens(text) if t not in sources and t not in GENERIC]
    if new_numbers or new_dates or new_names:
        return {
            "keep": False,
            "reason": "new_name_number_or_date",
            "new_numbers": new_numbers,
            "new_dates": new_dates,
            "new_names": new_names,
        }
    if unknown_terms:
        return {"keep": False, "reason": "terms_not_in_source", "terms": unknown_terms}
    return {"keep": True, "reason": "grounded"}


def dedupe(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        key = re.sub(r"\s+", " ", item.strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out
