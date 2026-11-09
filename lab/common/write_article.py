"""The actual writer: messy notes + a few sources -> one cited document.

Composes three pieces this session tested separately, each already safe on
its own, in the order that keeps them safe together:

1. `notes_to_findings` -- deterministic language-to-structure step. The
   system cannot reason over raw strings, so every sentence is reduced to
   content tokens and attributed to the source it shares the most
   distinctive tokens with, or left as the user's own uncited observation.
   No LLM, no embedding.
2. A bounded rewrite, ONE finding at a time. AUDIT.md ("does the project's
   OWN validated rewriter actually write anything here?", 2026-11-09) found
   live that asking the model to combine multiple findings into "one
   flowing paragraph" (lab.common.assemble.build_outline's default grouping
   of up to 4) makes it invent a relationship between facts that were never
   connected, every time. Restricting the rewrite unit to exactly one
   finding removes the invitation to relate anything -- confirmed live:
   8 of 10 findings passed the fidelity gate with zero fabrication, and the
   2 that fell back did so for ordinary reasons (an empty generation; a
   dropped hedge word), not invented relationships. This step only ever
   touches ONE already-attributed, already-cited fact; it never decides
   which facts relate to which, and never sees more than one at a time.
3. `assemble.assemble` -- deterministic again. Groups the (now individually
   rewritten-or-original) findings into sections and renders the document,
   with its own built-in coverage/citation-integrity checks. This step was
   never the problem; it was simply never fed input that wasn't already
   pre-structured, which step 1 now supplies.

Grouping findings into sections for readability (how `assemble.
build_outline` currently chunks every 4) is a presentation decision and is
kept fully separate from step 2's one-at-a-time rewrite -- a smarter,
topic-aware grouping could replace that chunking later without ever
touching the part proven safe here.
"""

from __future__ import annotations

from lab.common.assemble import assemble
from lab.common.notes_to_findings import notes_to_findings
from lab.common.rewriter_backends import rewrite_unit


def rewrite_findings_individually(
    findings: list[dict],
    checkpoint: str = "gemma3:270m",
) -> list[dict]:
    """Paraphrase each finding's statement on its own -- never alongside
    another finding, so the model is never asked to relate two facts to
    each other. Keeps the original statement (and reports why) when the
    fidelity gate rejects the rewrite; never a partial accept.
    """
    rewritten = []
    diagnostics = []
    for finding in findings:
        leaf = {
            "leaf_id": finding["finding_id"],
            "title": finding["finding_id"],
            "finding_ids": [finding["finding_id"]],
            "findings": [finding],
        }
        result = rewrite_unit(leaf, glossary={}, checkpoint=checkpoint, use_repair=True)
        new_statement = finding["statement"]
        if result["used_generative"]:
            # result["text"] still carries the trailing "[CITE]" marker
            # render_unit/assemble will re-append its own -- strip it here
            # so the citation is never duplicated downstream.
            cite = finding.get("citation") or finding.get("evidence_id")
            text = result["text"]
            marker = f"[{cite}]"
            if text.endswith(marker):
                text = text[: -len(marker)].strip()
            new_statement = text
        rewritten.append({**finding, "statement": new_statement})
        diagnostics.append({
            "finding_id": finding["finding_id"],
            "used_generative": result["used_generative"],
            "fallback_reason": result.get("fallback_reason"),
        })
    return rewritten, diagnostics


def write_article(
    messy_text: str,
    sources: list[dict],
    checkpoint: str = "gemma3:270m",
    rewrite: bool = True,
) -> dict:
    """messy_text (raw, possibly misspelled notes) + sources
    ([{"id","text"}, ...]) -> one cited, structurally-grounded document.

    `rewrite=True` (default) applies the one-finding-at-a-time bounded
    paraphrase from step 2 above; `rewrite=False` skips straight to
    deterministic assembly (last session's result) for comparison.
    """
    source_findings = [
        {"finding_id": f"S{i + 1}", "statement": s["text"], "citation": s["id"]}
        for i, s in enumerate(sources)
    ]
    note_findings = notes_to_findings(messy_text, sources)
    all_findings = source_findings + note_findings

    rewrite_diagnostics = None
    if rewrite:
        all_findings, rewrite_diagnostics = rewrite_findings_individually(all_findings, checkpoint)

    result = assemble(all_findings, task="generic", glossary={}, rewriter="deterministic")
    result["attribution"] = note_findings
    if rewrite_diagnostics is not None:
        result["rewrite_diagnostics"] = rewrite_diagnostics
    return result
