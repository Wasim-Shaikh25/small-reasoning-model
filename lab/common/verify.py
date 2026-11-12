"""Verification checks. A failure removes the claim or asks for another retrieval.

support_check/conflict_across/coverage_check/calculation_check/
bidirectional_nli/second_span_agrees/contradiction_queries/output_validator
moved to lab.tests.support on 2026-11-12 -- lab.common.brain never calls
any of them (it reimplements conflict_across's exact logic inline instead,
see brain.py's own comment at its conflict-check block, by deliberate
choice, not an oversight)."""

from __future__ import annotations

from lab.common.textutil import modals, numbers, span_in_passage

QUALIFIERS = ("clearly", "always", "obviously", "undoubtedly", "certainly")


def quote_check(span: str | None, passage: str | None) -> bool:
    return span_in_passage(span, passage)


def qualifier_added(source: str, output: str) -> list[str]:
    added = []
    src = source.lower()
    for word in QUALIFIERS:
        if word in output.lower() and word not in src:
            added.append(word)
    return added


def citation_markers(text: str) -> list[str]:
    import re

    return re.findall(r"\[([A-Za-z0-9_-]+)\]", text or "")


def strip_citation_markers(text: str) -> str:
    """Removes every `[marker]` lab.common.verify.citation_markers would
    find, collapsing the whitespace left behind. These markers are the
    pipeline's own internal grounding-verification bookkeeping (EXP-081
    caught them leaking as raw "[CHUNK0008]" ids; fixed by giving them a
    clean display form in lab.common.ingest.findings_from_chunks -- but
    the project owner's own call, once that was explained, was that
    *no* internal marker belongs in a final document a reader sees at
    all, clean or not: a real citation to an actual source (a statute, a
    paper) is a different thing entirely and stays, because it is part of
    the content, not an artifact of how this pipeline checked its own
    work). This function is the presentation-layer step that removes them
    right before a document is written for a reader -- every internal
    check (fidelity gate, coverage, citation integrity) still runs on the
    marker-containing text beforehand, unaffected.
    """
    import re

    return re.sub(r"\s*\[[A-Za-z0-9_-]+\]", "", text or "")


def modality_preserved(source: str, output: str) -> bool:
    return sorted(modals(source)) == sorted(modals(output))


def entity_number_check(source: str, output: str) -> dict:
    src_nums, out_nums = set(numbers(source)), set(numbers(output))
    return {
        "numbers_dropped": sorted(src_nums - out_nums),
        "numbers_added": sorted(out_nums - src_nums),
        "ok": not (src_nums - out_nums or out_nums - src_nums),
    }


