"""Raw document in, ready-to-reason passages out -- the step the project
owner asked for by name: "once we give prompt or document it will
instantly become... all index and everything... needed" before reasoning
starts.

What that actually requires, checked against how this repo already
works rather than assumed: lab.common.index.Index and lab.common.
semantic_index.SemanticIndex already build their structures on the fly
from whatever passage list they're given, at query time -- there is no
separate, persisted "build the index" step inside brain.reason() itself
(lab.common.store.Store/get_or_build, added 2026-11-01, extends EXP-022's
save/load pattern for a caller who wants that persistence explicitly --
see that module's own docstring; reason() itself still always builds
in-process from whatever passages it's given). Same for the entity
graph (lab.common.graph_index.build_entity_graph): built fresh from a
passage list each time by reason() itself, not persisted (again,
Store.build(use_graph=True) can persist one if a caller wants it).
So the one genuinely missing piece, the one this module supplies, is
turning raw document text into that passage-list shape at all --
chunking -- not a new indexing stage. Everything downstream (Index,
SemanticIndex, build_entity_graph, lab.common.brain.reason) already
works the moment a document is in that shape; this is what gets it
there.

NAME COLLISION, flagged by the 2026-11-03 reasoning-layer audit
(AUDIT.md): `chunk_document` below shares a name with
lab.common.chunking.chunk_document, a structure-aware, overlapping-
window chunker with a different signature and a much richer per-chunk
shape -- see that module's own docstring for the full comparison.
**This is the chunker brain.reason()'s live document_write path
actually uses** (`findings_from_chunks` below, imported directly by
brain.py); chunking.py's version is exercised only by standalone
explorations, never by reason() itself.
"""

from __future__ import annotations

import re


def chunk_document(raw_text: str, max_words_per_chunk: int = 120) -> list[dict]:
    """Splits on blank lines (paragraphs) first -- the natural unit a real
    document is already written in -- then, only if a paragraph is long
    enough that a single bounded rewrite_unit call would struggle with it
    (EXP-048 onward measured the rewriter's own reliability degrading
    well before 120 words), splits that one paragraph further at sentence
    boundaries. Never splits a sentence in half.

    Returns passages shaped exactly as lab.common.brain.reason and
    lab.common.longform.write_long_document already expect: a flat list
    of {"id", "text"} dicts, no new fields, no separate indexing call
    needed before passing this straight to either of them.
    """
    from lab.common.textutil import sentences

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw_text or "") if p.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph.split()) <= max_words_per_chunk:
            chunks.append(paragraph)
            continue
        current: list[str] = []
        current_words = 0
        for sentence in sentences(paragraph):
            sentence_words = len(sentence.split())
            if current and current_words + sentence_words > max_words_per_chunk:
                chunks.append(" ".join(current))
                current, current_words = [], 0
            current.append(sentence)
            current_words += sentence_words
        if current:
            chunks.append(" ".join(current))

    return [{"id": f"CHUNK{i:04d}", "text": chunk} for i, chunk in enumerate(chunks)]


def findings_from_chunks(chunks: list[dict]) -> list[dict]:
    """The only sanctioned way to turn chunk_document's output into the
    findings shape lab.common.longform/lab.common.assemble expect.

    chunk_document's own "id" field (e.g. "CHUNK0008") is an internal
    bookkeeping label for this module's own chunking step -- it was never
    meant to be read by the document's eventual reader. A first version of
    this pipeline's own test script built findings by hand with
    `"citation": c["id"]`, which put that internal id directly into
    lab.common.assemble.render_unit's "[{cite}]" marker and so into the
    rendered document body and citation index verbatim (caught inspecting
    a real GDPR rewrite's output). Citation markers are presentation, not
    internals: whatever naming scheme this module's chunking happens to
    use is exactly the kind of implementation detail a document's reader
    should never see, so this function hard-codes a clean, sequential,
    content-free citation label ("1", "2", "3", ...) instead -- stable
    and unique (what citation_integrity/coverage_report actually need),
    carrying no information about how the text was chunked.

    finding_id keeps chunk_document's own id -- that field is internal
    bookkeeping only (coverage_report tracks it, nothing renders it into
    the document text), so there is nothing for it to leak.
    """
    return [{"finding_id": c["id"], "statement": c["text"], "citation": str(i + 1)} for i, c in enumerate(chunks)]


