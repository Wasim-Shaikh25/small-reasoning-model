"""Structure-aware chunking. Summaries are extractive sentences, never written prose."""

from __future__ import annotations

import hashlib
import re

from lab.common.textutil import content_tokens, sentences, word_count

HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+|(?:[0-9]+(?:\.[0-9]+)*)\s+|\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z].*|[A-Z][A-Z0-9 ,/&-]{3,60})$"
)
PARTY_RE = re.compile(r"\b(lessee|lessor|residing at|having its office|party of the)\b", re.I)
DEF_RE = re.compile(r"\bmeans\b|\(the [A-Z][a-z]+\)", re.I)
SIG_RE = re.compile(r"\b(signature|signed by|in witness)\b", re.I)
SCHED_RE = re.compile(r"\b(schedule|annexure|appendix)\b", re.I)
CLAUSE_RE = re.compile(r"^\s*\d+(?:\.\d+)*\s+")
PAGE_RE = re.compile(r"^page\s+(\d+)\s*$", re.I)


def version_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_type_of(block: str, heading: str) -> str:
    sample = f"{heading}\n{block[:400]}"
    head = heading.lower()
    if SIG_RE.search(sample):
        return "signature"
    if SCHED_RE.search(heading) or SCHED_RE.match(block.strip()[:40]):
        return "schedule"
    party_block = ("residing at" in sample.lower()) or ("having its office" in sample.lower())
    if party_block:
        return "party_block"
    if "means" in block.lower() or "definition" in head:
        return "definition"
    return "clause"


def _blocks(text: str) -> list[tuple[str, str, int]]:
    """Return (heading, body, page) sections."""
    heading = "Document"
    page = 1
    buf: list[str] = []
    out: list[tuple[str, str, int]] = []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            out.append((heading, body, page))

    for line in text.splitlines():
        stripped = line.strip()
        page_match = PAGE_RE.match(stripped)
        if page_match:
            flush()
            buf = []
            page = int(page_match.group(1))
            continue
        if stripped and (HEADING_RE.match(stripped) or stripped.endswith(":")) and word_count(stripped) <= 12:
            flush()
            buf = []
            heading = stripped.lstrip("#").strip()
            continue
        buf.append(line)
    flush()
    return out


def _split_words(text: str, max_words: int, overlap_ratio: float) -> list[tuple[str, int, int]]:
    words = text.split()
    if len(words) <= max_words:
        return [(text.strip(), 0, len(text))] if text.strip() else []
    overlap = max(1, int(max_words * overlap_ratio))
    step = max(1, max_words - overlap)
    spans = []
    # Map word index to char offset approximately by scanning.
    starts = []
    pos = 0
    raw = text
    for word in words:
        idx = raw.find(word, pos)
        starts.append(idx if idx >= 0 else pos)
        pos = (idx if idx >= 0 else pos) + len(word)
    i = 0
    while i < len(words):
        j = min(len(words), i + max_words)
        start = starts[i]
        end = starts[j - 1] + len(words[j - 1])
        spans.append((text[start:end].strip(), start, end))
        if j >= len(words):
            break
        i += step
    return spans


def extractive_summary(text: str, max_sentences: int = 2) -> str:
    sents = sentences(text)
    if not sents:
        return ""
    scored = []
    for sent in sents:
        scored.append((len(content_tokens(sent)), sent))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    chosen = [sent for _, sent in scored[:max_sentences]]
    # Keep original order.
    return " ".join(s for s in sents if s in chosen)


def chunk_document(
    text: str,
    doc_id: str,
    *,
    min_words: int = 40,
    max_words: int = 120,
    overlap_ratio: float = 0.12,
) -> list[dict]:
    digest = version_hash(text)
    chunks = []
    section_counts: dict[str, int] = {}
    for heading, body, page in _blocks(text):
        pieces = _split_words(body, max_words, overlap_ratio)
        if not pieces and body.strip():
            pieces = [(body.strip(), 0, len(body))]
        for local_i, (piece, start, end) in enumerate(pieces):
            if word_count(piece) < 3:
                continue
            section_counts[heading] = section_counts.get(heading, 0) + 1
            ordinal = section_counts[heading]
            ctype = chunk_type_of(piece, heading)
            summary = extractive_summary(piece)
            chunks.append(
                {
                    "chunk_id": f"{doc_id}-p{page}-c{ordinal}",
                    "doc_id": doc_id,
                    "version_hash": digest,
                    "page": page,
                    "section_path": [heading],
                    "char_offsets": [start, end],
                    "chunk_type": ctype,
                    "text": piece,
                    "word_count": word_count(piece),
                    "summary": summary,
                    "summary_is_evidence": False,
                    "summary_sentences_are_substrings": all(
                        s in piece for s in sentences(summary)
                    ),
                    "below_min_words": word_count(piece) < min_words,
                }
            )
            del local_i
    return chunks
