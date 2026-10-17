"""Long-form document writing: the two named gaps (EXP-052, EXP-053) that
sat between "the architecture scales" (EXP-018: 42,506 words, zero
sentences generated) and "the generative rewriter scales" (EXP-077: real
degradation at just 80 leaves) and a genuinely usable multi-page writer.

Wires together pieces already built and separately measured, changing
none of them:
  - lab.common.entities.detect_primary: groups findings by the entity
    their content is actually about, so the outline's shape comes from
    the data, not from an arbitrary 4-per-leaf count (EXP-052's actual
    goal). A first version of this module tried a cheaper shortcut --
    titling leaves from the ask's own subquestions, zipped in by index,
    after the count-based bucketing had already run -- and EXP-078
    caught it producing a title that didn't describe its own leaf's
    content: the bucketing was still arbitrary, only the label on top of
    it had changed. Grouping by entity first is the real fix, not a
    cosmetic one.
  - lab.common.assemble.build_outline: still owns bucketing whatever
    findings have no clear single-entity grouping (a global policy
    passage, say) into the original 4-per-leaf shape, unchanged -- the
    fallback for content a per-entity outline can't apply to.
  - lab.common.rewriter_backends.rewrite_unit: still owns the bounded,
    fidelity-gated per-leaf generation, unchanged -- model-agnostic by
    construction (EXP-076), so this module works with any registered
    checkpoint.
  - lab.common.working_memory.WorkingMemory: EXP-053's actual mechanism
    -- a running digest of every earlier page's claims (subject-verb-
    object triples only, never full text), checked before each new page
    is added, never after.
  - lab.common.document_writer.write_document: still owns the final
    formatted file, unchanged.

A consistency flag is reported, never silently resolved either way --
the same posture every other verification step in this repo takes.
"""

from __future__ import annotations

from pathlib import Path

from lab.common.assemble import build_outline
from lab.common.document_writer import write_document
from lab.common.entities import detect_primary
from lab.common.rewriter_backends import rewrite_unit
from lab.common.working_memory import WorkingMemory


MAX_FINDINGS_PER_ENTITY_LEAF = 4


def _entity_outline(findings: list[dict]) -> tuple[list[dict], list[dict]]:
    """One or more leaves per distinct person/organization the findings
    are about, in first-seen order, titled with that entity's own name --
    not a generic "Section N". A finding naming no person/org (a global
    policy, a date-only statement) is left for the caller's count-based
    fallback instead of being forced into a group it doesn't belong to.

    A prolific entity (more than MAX_FINDINGS_PER_ENTITY_LEAF findings) is
    still split across several leaves, same cap EXP-018's bucketing
    already uses -- not just to bound leaf size, but because a real
    book-length document keeps the same entity's facts spread across
    genuinely different sections (an employee directory entry and a
    separate audit note, say), which is also the only way this entity's
    own facts can end up on two different "pages" for
    lab.common.working_memory's cross-page check to have anything to
    compare -- a single merged leaf has nothing to be inconsistent
    *across*, only within, which this module's fidelity gate (not the
    cross-page check) is responsible for.
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    leftover: list[dict] = []
    for finding in findings:
        mentions = [m for m in detect_primary(finding["statement"]) if m["label"] in ("person", "organization")]
        if not mentions:
            leftover.append(finding)
            continue
        key = mentions[0]["text"]
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(finding)
    leaves = []
    for key in order:
        entity_findings = groups[key]
        chunks = [entity_findings[i : i + MAX_FINDINGS_PER_ENTITY_LEAF] for i in range(0, len(entity_findings), MAX_FINDINGS_PER_ENTITY_LEAF)]
        for chunk_index, chunk in enumerate(chunks):
            title = key if len(chunks) == 1 else f"{key} ({chunk_index + 1})"
            leaves.append({"leaf_id": f"E{len(leaves):04d}", "title": title, "finding_ids": [f["finding_id"] for f in chunk], "findings": chunk})
    return leaves, leftover


def write_long_document(
    ask: str,
    findings: list[dict],
    glossary: dict | None = None,
    task: str = "lookup",
    checkpoint: str = "flan-t5-small",
    title: str = "Document",
    out_path: Path | None = None,
) -> dict:
    """Writes one long document from `findings`, page by page, checking
    cross-page consistency as it goes.

    `ask` is accepted and kept in the signature but not yet used to shape
    the outline -- a first version used it to title leaves by zipping its
    subquestions in by index, which EXP-078 caught producing titles that
    didn't match their own leaf's content once outlining switched to
    entity-grouping. Said here rather than left silently unused: this is
    a real gap, not a finished design, and the honest state is "not used
    yet," not a half-working mechanism dressed up as ask-driven.

    Returns {"document_result", "consistency_flags", "rewrite_diagnostics",
    "working_memory"} -- `consistency_flags` is never empty-by-default-
    assumption; it is whatever WorkingMemory actually found, reported as
    measured. If `out_path` is given, also writes the formatted file
    (lab.common.document_writer) and includes its result.
    """
    glossary = glossary or {}
    entity_leaves, leftover_findings = _entity_outline(findings)
    leftover_leaves = build_outline(leftover_findings, task) if leftover_findings else []
    outline = entity_leaves + leftover_leaves

    memory = WorkingMemory()
    rendered_units = []
    rewrite_diagnostics = []
    consistency_flags = []

    for leaf in outline:
        result = rewrite_unit(leaf, glossary, checkpoint=checkpoint)
        unit_text = result["text"] if result["text"].startswith(leaf["title"]) else f"{leaf['title']}\n{result['text']}"
        rendered_units.append(unit_text)
        rewrite_diagnostics.append(
            {
                "leaf_id": leaf["leaf_id"],
                "used_generative": result["used_generative"],
                "fallback_reason": result["fallback_reason"],
            }
        )

        citation_ids = [f.get("citation") or f.get("evidence_id") for f in leaf["findings"]]
        flags = memory.check_and_remember_page(leaf["leaf_id"], result["text"], citation_ids)
        consistency_flags.extend(flags)

    document_text = "\n\n".join(rendered_units)
    assembled = {"document": document_text}

    document_result = None
    if out_path is not None:
        document_result = write_document(title, assembled, findings, task, out_path)

    return {
        "document": document_text,
        "document_result": document_result,
        "consistency_flags": consistency_flags,
        "rewrite_diagnostics": rewrite_diagnostics,
        "working_memory": memory.to_dict(),
    }
