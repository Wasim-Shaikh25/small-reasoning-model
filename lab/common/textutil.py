"""Text helpers. No language model. Strings are data."""

from __future__ import annotations

import re

STOP = {
    "a", "an", "the", "of", "and", "or", "to", "in", "on", "for", "with", "by",
    "from", "at", "as", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "their", "his", "her",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "does", "do", "did", "if", "then", "than", "into", "over", "under", "about",
    "please", "also", "not", "no", "nor", "so", "such", "there", "here",
}

NUM_RE = re.compile(r"\b\d[\d,./-]*\b")
MODAL_RE = re.compile(
    r"\b(not|no|shall|may|must|unless|except|only|provided)\b", re.I
)
NEG_RE = re.compile(
    r"\b(not|no|never|none|neither|without)\b|\bshall not\b|\bmust not\b|"
    r"\bmay not\b|\bn't\b",
    re.I,
)
TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.I)
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"\s+\d{4}|"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},?\s+\d{4})\b",
    re.I,
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "")]


def content_tokens(text: str) -> list[str]:
    return [t for t in tokens(text) if t not in STOP and len(t) > 1]


def word_count(text: str) -> int:
    return len((text or "").split())


def numbers(text: str) -> list[str]:
    return NUM_RE.findall(text or "")


def modals(text: str) -> list[str]:
    return [m.lower() for m in MODAL_RE.findall(text or "")]


def polarity_flipped(a: str, b: str) -> bool:
    return (len(NEG_RE.findall(a or "")) % 2) != (len(NEG_RE.findall(b or "")) % 2)


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _token_close(left: str, right: str) -> bool:
    if left == right:
        return True
    if len(left) >= 4 and len(right) >= 4 and (left.startswith(right) or right.startswith(left)):
        return True
    return False


def coverage(needles: list[str], hay: list[str]) -> float:
    if not needles:
        return 0.0
    hit = 0
    for needle in needles:
        if any(_token_close(needle, item) for item in hay):
            hit += 1
    return hit / len(needles)


def span_in_passage(span: str | None, passage: str | None) -> bool:
    if not span or not passage:
        return False
    return normalize(span) in normalize(passage)


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if p.strip()]


def find_span(text: str, fragment: str) -> tuple[int, int] | None:
    if not text or not fragment:
        return None
    idx = text.find(fragment)
    if idx < 0:
        low = text.lower()
        idx = low.find(fragment.lower())
        if idx < 0:
            return None
    return idx, idx + len(fragment)
