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
    """
    outline = build_outline(findings, task)
    cite_markers = citation_markers(assembled["document"])
    toc_titles = leaf_titles if leaf_titles is not None else [leaf["title"] for leaf in outline]

    sections = [
        f"# {title}",
        "## Table of Contents",
        "\n".join(f"{i + 1}. {t}" for i, t in enumerate(toc_titles)),
        "## Document",
        assembled["document"],
    ]
    if include_citation_index:
        sections += ["## Citation Index", _citation_index(cite_markers)]
    rendered = "\n\n".join(sections) + "\n"

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")

    return {
        "path": str(out_path),
        "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "sections": len(toc_titles),
        "word_count": len(rendered.split()),
        "citations_indexed": len(cite_markers),
    }
