"""The capstone step's other output format: a real Word .docx file, not
just Markdown. Same input, same structural decisions as
lab.common.document_writer -- a title, a table of contents, the
assembled body, a citation index -- just rendered with python-docx
instead of string-joining into a .md file. Every structural fact (which
leaf, which citation, in what order) still comes from lab.common.
assemble/lab.common.longform; this module only chooses heading styles,
paragraph breaks, and a TOC list -- formatting, never content.
"""

from __future__ import annotations

from pathlib import Path

from lab.common.assemble import build_outline
from lab.common.verify import citation_markers


def write_docx(title: str, assembled: dict, findings: list[dict], task: str, out_path: Path, leaf_titles: list[str] | None = None, include_citation_index: bool = True) -> dict:
    """`leaf_titles`, when given (lab.common.longform already knows its
    own leaves' real titles), is used for the table of contents instead
    of rebuilding a generic outline -- so a document written with
    entity-grouped sections gets a TOC that matches those sections, not
    lab.common.assemble.build_outline's own 4-per-leaf "Section N"
    naming, which is a different grouping entirely for a long-form
    document.

    `include_citation_index` defaults to True, matching lab.common.
    document_writer.write_document's identical parameter and for the same
    reason: lab.common.longform.write_long_document -- the end-reader-
    facing path -- passes `assembled["document"]` already stripped of
    internal citation markers and include_citation_index=False, so no
    pipeline-internal id reaches the .docx a reader opens.
    """
    from docx import Document

    doc = Document()
    doc.add_heading(title, level=0)

    doc.add_heading("Table of Contents", level=1)
    titles = leaf_titles if leaf_titles is not None else [leaf["title"] for leaf in build_outline(findings, task)]
    for leaf_title in titles:
        doc.add_paragraph(leaf_title, style="List Number")

    doc.add_heading("Document", level=1)
    for block in assembled["document"].split("\n\n"):
        lines = block.split("\n")
        if lines and lines[0] in titles:
            doc.add_heading(lines[0], level=2)
            body_lines = lines[1:]
        else:
            body_lines = lines
        for line in body_lines:
            if line.strip():
                doc.add_paragraph(line)

    markers = sorted(set(citation_markers(assembled["document"])))
    if include_citation_index:
        doc.add_heading("Citation Index", level=1)
        for marker in markers:
            doc.add_paragraph(f"[{marker}]", style="List Bullet")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))

    return {
        "path": str(out_path),
        "sections": len(titles),
        "citations_indexed": len(markers),
    }
