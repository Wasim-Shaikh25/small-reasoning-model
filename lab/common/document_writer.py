"""The capstone step lab.common.assemble never had: writing one complete,
formatted document to disk.

lab.common.assemble.assemble() already draws the line this project insists
on everywhere else -- Python decides every structural fact (which findings
go in which leaf, how many findings per leaf, citation/coverage/repetition
checks, the final string's byte-for-byte content), and a model or template
contributes only a leaf's prose text, never a layout decision. What it never
did was write an actual file: `assemble()` returns a dict with a `document`
string in memory, nothing more. This module is that last, missing step --
still no new judgment calls, only formatting ones: a title, a table of
contents built from the same deterministic outline `assemble()` already
computed, the assembled body, and a citation index. Every one of those is
derived from data already produced upstream, not decided here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from lab.common.assemble import build_outline
from lab.common.verify import citation_markers


def _citation_index(markers: list[str]) -> str:
    return "\n".join(f"- [{m}]" for m in sorted(set(markers)))


def write_document(title: str, assembled: dict, findings: list[dict], task: str, out_path: Path, leaf_titles: list[str] | None = None, include_citation_index: bool = True) -> dict:
    """Render assembled findings (lab.common.assemble.assemble()'s output) as
    one formatted Markdown file and write it to `out_path`.

    `findings` and `task` must be the identical arguments assemble() was
    called with -- build_outline is deterministic, so rebuilding the outline
    here (rather than threading it through assemble()'s return value) always
    reproduces the same leaf titles, at the cost of one cheap recomputation
    instead of changing assemble()'s existing return contract.

    `leaf_titles`, when given, is used for the table of contents instead of
    the recomputed outline -- lab.common.longform already knows its own
    leaves' real (entity-grouped) titles, and rebuilding build_outline's own
    4-per-leaf "Section N" numbering here produced a table of contents that
    didn't match the document's actual section headers (caught inspecting a
    real GDPR rewrite's output, same mismatch lab.common.docx_writer already
    had a leaf_titles parameter to avoid).

    `include_citation_index` defaults to True so this function's existing
    contract (EXP-074, which checks the index exactly matches the markers
    present in `assembled["document"]`) is unchanged for any direct caller.
    lab.common.longform.write_long_document -- the actual end-reader-facing
    path -- passes `assembled["document"]` already stripped of markers
    (lab.common.verify.strip_citation_markers) and include_citation_index
    =False: the project owner's call that a pipeline's own internal
    grounding-verification bookkeeping belongs in the checks that already
    ran before this function was called, never in a file a reader opens. A
    real citation to an actual outside source, if a template ever needs
    one, is a different thing -- part of the content, written into a
    finding's own statement text, not this internal marker.

    Writes straight to `out_path` as each piece (title, TOC, body,
    citation index) is produced, instead of concatenating everything into
    one `rendered` string first and writing that in a single call (2026-
    11-11) -- for a long document, that used to mean two full-document-
    sized strings alive at once (`assembled["document"]`, already built by
    the caller, plus this function's own copy of the same text wrapped in
    headers) purely to hand the same bytes to `write_text` once. The file
    on disk is byte-identical either way; only the peak memory this
    function itself adds on top of what the caller already holds changes.
    `assembled["document"]` is still one full string in memory by the time
    this function is called -- that part is the caller's
    (lab.common.longform.write_long_document's) contract, not something a
    streaming write here can undo; see that module's docstring for why.
    """
    outline = build_outline(findings, task)
    document_text = assembled["document"]
    cite_markers = citation_markers(document_text)
    toc_titles = leaf_titles if leaf_titles is not None else [leaf["title"] for leaf in outline]

    head = "\n\n".join(
        [
            f"# {title}",
            "## Table of Contents",
            "\n".join(f"{i + 1}. {t}" for i, t in enumerate(toc_titles)),
            "## Document",
        ]
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    hasher = hashlib.sha256()
    word_count = 0

    with out_path.open("w", encoding="utf-8") as fh:
        def _write(chunk: str) -> None:
            nonlocal word_count
            fh.write(chunk)
            hasher.update(chunk.encode("utf-8"))
            word_count += len(chunk.split())

        _write(head)
        _write("\n\n")
        _write(document_text)
        if include_citation_index:
            _write("\n\n## Citation Index\n\n")
            _write(_citation_index(cite_markers))
        _write("\n")

    return {
        "path": str(out_path),
        "sha256": hasher.hexdigest(),
        "sections": len(toc_titles),
        "word_count": word_count,
        "citations_indexed": len(cite_markers),
    }
