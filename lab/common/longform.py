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
from lab.common.doc_tools import assign_findings_to_sections, check_template_contracts, load_template
from lab.common.document_writer import write_document
from lab.common.entities import detect_primary
from lab.common.rewriter_backends import rewrite_unit
from lab.common.working_memory import WorkingMemory


MAX_FINDINGS_PER_ENTITY_LEAF = 4


def _template_outline(template: dict, findings: list[dict]) -> list[dict]:
    """The outline a registered lab.common.doc_tools template dictates,
    instead of entity-grouping or arbitrary count-bucketing: one leaf per
    template section, in the template's own declared order, titled with
    the section's own title. Each leaf also carries the section's own
    `instructions` (the project owner's actual ask: give the rewriter the
    document's real formatting rules instead of a generic combine-these-
    findings instruction, so it doesn't have to guess a legal notice's or
    a lecture note's shape from its own training data).

    An empty section (no finding routed to it) is still included, not
    dropped -- a visibly empty "Demand" section in a legal notice is a
    real, reportable fact about the input findings, not a layout detail
    to hide.
    """
    sections_with_findings, _ = assign_findings_to_sections(template, findings)
    return [
        {
            "leaf_id": f"T{i:04d}",
            "title": section["title"],
            "finding_ids": [f["finding_id"] for f in section["findings"]],
            "findings": section["findings"],
            "section_instructions": section["instructions"],
        }
        for i, section in enumerate(sections_with_findings)
    ]


def _entity_outline(findings: list[dict], use_real_ner: bool = False) -> tuple[list[dict], list[dict]]:
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
        mentions = [m for m in detect_primary(finding["statement"], use_real_ner=use_real_ner) if m["label"] in ("person", "organization")]
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
    docx_out_path: Path | None = None,
    use_real_ner: bool = False,
    template_id: str | None = None,
    use_real_nli: bool = False,
    use_repair: bool = False,
    plain_english: bool = False,
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

    `template_id`, when given (a registered lab.common.doc_tools template,
    e.g. "legal_notice" or "college_notes"), replaces entity-grouping
    entirely: the outline comes from the template's own declared sections,
    in its own order, each carrying its own per-section instructions
    instead of the generic "combine these findings" prompt every other
    leaf gets. When omitted (the default), behavior is unchanged from
    before this parameter existed.

    `use_real_nli` (default False) passes straight through to every leaf's
    `rewrite_unit`/`fidelity_gate` call -- opt-in real DeBERTa-v3 MNLI
    entailment checking instead of the classical lexical judge (2026-11-03
    reasoning-layer audit, AUDIT.md) -- AND (2026-11-10) to `WorkingMemory.
    check_and_remember_page`'s own NLI-contradiction gate: a same-subject-
    same-verb-different-object candidate is only kept in `consistency_
    flags` if its two underlying sentences actually show NLI contradiction
    evidence, not just coincidence. See `lab.common.working_memory`'s
    module docstring ("Follow-up 2026-11-10") for the measured EXP-081
    false-positive rate this fixes (15/16 on that real document).

    `use_repair` (default False) passes through too -- opt-in use of each backend's own repair mechanism
    (flan-t5-small's retry-with-feedback, gemma3:270m's citation-splice)
    instead of this project's dispatcher bypassing both (same audit,
    rewriter_backends.rewrite_unit's own docstring has the full story).
    Both default False, so every existing measured fidelity-pass rate
    stays exactly as recorded unless a caller explicitly opts in.

    `plain_english` (default False, same opt-in discipline): runs each
    rendered leaf's text through `lab.common.plain_language.
    simplify_document` -- formal-vocabulary substitution plus per-
    sentence passive-to-active/connective-splitting, each gated by
    bidirectional NLI entailment (see that module and `grammar_logic.py`
    for exactly what is and isn't attempted). Recorded per-leaf in
    `rewrite_diagnostics` as `plain_english_result`; never applied to a
    leaf with no findings (nothing to simplify).

    Returns {"document_result", "consistency_flags", "rewrite_diagnostics",
    "working_memory"} -- `consistency_flags` is never empty-by-default-
    assumption; it is whatever WorkingMemory actually found, reported as
    measured. If `out_path` is given, also writes the formatted file
    (lab.common.document_writer) and includes its result.

    `contract_violations` (2026-11-10): when `template_id` is given, every
    section with a declared `contract` (lab.common.doc_tools.
    check_section_contract) is checked against the findings actually
    routed to it; this list holds only the sections that FAILED their own
    contract (empty list if every checked section passed, `None` -- not
    an empty list -- when no `template_id` was given at all, so a caller
    can tell "nothing to check" from "checked, all passed"). Never blocks
    writing the document -- same "report, don't silently resolve" posture
    `consistency_flags` already takes.
    """
    glossary = glossary or {}
    contract_violations = None
    if template_id is not None:
        template = load_template(template_id)
        outline = _template_outline(template, findings)
        # Same sections, same per-section findings `_template_outline` just
        # built its leaves from -- re-paired here (rather than having
        # `_template_outline` return them) so a caller who never passes
        # `template_id` pays nothing for this, and the contract check
        # itself stays in lab.common.doc_tools, not duplicated here.
        contract_checks = check_template_contracts(
            template, [{**section, "findings": leaf["findings"]} for section, leaf in zip(template["sections"], outline)]
        )
        contract_violations = [c for c in contract_checks if not c["ok"]]
    else:
        entity_leaves, leftover_findings = _entity_outline(findings, use_real_ner=use_real_ner)
        leftover_leaves = build_outline(leftover_findings, task) if leftover_findings else []
        outline = entity_leaves + leftover_leaves

    memory = WorkingMemory()
    rendered_units = []
    rewrite_diagnostics = []
    consistency_flags = []

    for leaf in outline:
        if not leaf["findings"]:
            # An empty template section: nothing to rewrite or fidelity-
            # check, and feeding the generative model zero source text
            # would make its fidelity checks meaningless. Reported
            # explicitly ("no_findings"), not silently skipped.
            unit_text = leaf["title"]
            rewrite_diagnostics.append({"leaf_id": leaf["leaf_id"], "used_generative": False, "fallback_reason": ["no_findings"], "plain_english_result": None})
            rendered_units.append(unit_text)
            continue

        result = rewrite_unit(leaf, glossary, checkpoint=checkpoint, ask=leaf.get("section_instructions"), use_real_nli=use_real_nli, use_repair=use_repair)
        unit_text = result["text"] if result["text"].startswith(leaf["title"]) else f"{leaf['title']}\n{result['text']}"

        plain_english_result = None
        if plain_english:
            from lab.common.plain_language import simplify_document

            plain_english_result = simplify_document(unit_text)
            unit_text = plain_english_result["text"]

        rendered_units.append(unit_text)
        rewrite_diagnostics.append(
            {
                "leaf_id": leaf["leaf_id"],
                "used_generative": result["used_generative"],
                "fallback_reason": result["fallback_reason"],
                "plain_english_result": plain_english_result,
            }
        )

        citation_ids = [f.get("citation") or f.get("evidence_id") for f in leaf["findings"]]
        flags = memory.check_and_remember_page(leaf["leaf_id"], result["text"], citation_ids, use_real_nli=use_real_nli)
        consistency_flags.extend(flags)

    document_text = "\n\n".join(rendered_units)
    assembled = {"document": document_text}

    # The internal grounding-verification bookkeeping (citation markers)
    # stops here -- lab.common.working_memory's consistency check above
    # already ran on the marker-containing text, and every per-leaf
    # fidelity_gate call already checked citation integrity during
    # generation. Nothing past this point is a reader of this document:
    # strip_citation_markers (lab.common.verify) is the project owner's
    # own call, once the internal-id leak was explained, that no pipeline-
    # internal marker belongs in a file a reader opens, clean display form
    # or not -- only a real citation to an actual outside source, written
    # as part of a finding's own statement text, would ever belong there.
    from lab.common.verify import strip_citation_markers

    reader_facing_document = strip_citation_markers(document_text)
    reader_facing_assembled = {"document": reader_facing_document}

    document_result = None
    if out_path is not None:
        document_result = write_document(title, reader_facing_assembled, findings, task, out_path, leaf_titles=[leaf["title"] for leaf in outline], include_citation_index=False)

    docx_result = None
    if docx_out_path is not None:
        from lab.common.docx_writer import write_docx

        docx_result = write_docx(title, reader_facing_assembled, findings, task, docx_out_path, leaf_titles=[leaf["title"] for leaf in outline], include_citation_index=False)

    # Same dependency-tree shape lab.common.brain.reason's own signal-
    # chain stages already build ({"id","kind","summary","depends_on"}):
    # one "document_leaf" node per leaf (WorkingMemory.dependency_tree,
    # depending on that leaf's own source findings), plus one
    # "contradiction_flag" node per cross-page conflict already found
    # above -- an explicit edge between the two leaves whose claims
    # disagree, the one place this module already connects one page's
    # truth to another's.
    dependency_tree = memory.dependency_tree()
    for flag in consistency_flags:
        dependency_tree.append(
            {
                "id": f"contradiction:{flag['leaf_id']}:{flag['subject']}:{flag['verb_lemma']}",
                "kind": "contradiction_flag",
                "summary": f"{flag['subject']} {flag['verb_lemma']} {flag['new_object']!r} conflicts with leaf {flag['conflicts_with_leaf_id']}'s earlier {flag['prior_object']!r}",
                "depends_on": [f"leaf:{flag['leaf_id']}", f"leaf:{flag['conflicts_with_leaf_id']}"],
            }
        )

    return {
        "document": document_text,
        "document_for_reader": reader_facing_document,
        "document_result": document_result,
        "docx_result": docx_result,
        "consistency_flags": consistency_flags,
        "rewrite_diagnostics": rewrite_diagnostics,
        "working_memory": memory.to_dict(),
        "dependency_tree": dependency_tree,
        "contract_violations": contract_violations,
    }
