"""Renders a concept result (lab.common.concept_tools.teach_and_run's
`result`, a flat list of dicts or a dict) into the three output shapes
asked for: JSON (exact structure, for another program to consume), a
Markdown file (for a person to read, or a doc pipeline to include), and a
.docx file (lab.common.docx_writer already renders full assembled
documents with sections and citations; this is the lighter-weight sibling
for a single concept result, not a long document).
"""

from __future__ import annotations

import json
from pathlib import Path


def render_json(result: list | dict) -> str:
    return json.dumps(result, indent=2, default=str, ensure_ascii=False)


def _rows(result: list | dict) -> list[dict]:
    if isinstance(result, dict):
        return [result]
    return [r for r in result if isinstance(r, dict)] or [{"value": r} for r in result]


def render_md(result: list | dict, title: str) -> str:
    lines = [f"# {title}", ""]
    for row in _rows(result):
        lines.append("- " + "; ".join(f"**{k}**: {v}" for k, v in row.items() if v is not None))
    return "\n".join(lines) + "\n"


def render_docx(result: list | dict, title: str, out_path: str | Path) -> str:
    from docx import Document

    doc = Document()
    doc.add_heading(title, level=1)
    for row in _rows(result):
        doc.add_paragraph("; ".join(f"{k}: {v}" for k, v in row.items() if v is not None))
    out_path = str(out_path)
    doc.save(out_path)
    return out_path


RENDERERS = {"json": render_json, "md": render_md, "docx": render_docx}
