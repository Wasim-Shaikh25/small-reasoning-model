"""EXP-074: the mandatory prompt contract and the document-assembly
capstone step, measured rather than assumed.

Two things proven here:

1. lab.common.prompt_contract is now the one shared way every generative
   call site in this repo builds a prompt -- but lab.common.real_rewriter's
   migration onto it (labeled=False) must produce byte-identical prompts to
   what every fidelity measurement since EXP-048 was taken against.
   Reformatting a prompt a small model was measured against, even just
   adding section headers, is a real risk to that model's behavior, not a
   cosmetic no-op -- so this checks equality directly rather than assuming
   a refactor is safe.

2. lab.common.document_writer is the step lab.common.assemble never had:
   writing one complete, formatted file to disk (title, table of contents,
   body, citation index), with every structural decision made by Python,
   not a model. Checked here: the table of contents has exactly as many
   entries as there are leaves, and the citation index contains exactly the
   citation markers that appear in the assembled document -- no more, no
   fewer.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.assemble import assemble, build_outline
from lab.common.document_writer import write_document
from lab.common.harness import Run
from lab.common.real_rewriter import build_prompt
from lab.common.verify import citation_markers

FILES = [
    "lab/exp_074_document_contract/run.py",
    "lab/common/prompt_contract.py",
    "lab/common/document_writer.py",
    "lab/common/real_rewriter.py",
    "lab/common/assemble.py",
    "data/exp_074_document_contract/results.json",
]

LEAVES_FOR_PROMPT_CHECK = [
    {"leaf_id": "L1", "title": "Section 1", "finding_ids": ["F1"], "findings": [{"finding_id": "F1", "statement": "The rent is INR 25000.", "citation": "C1"}]},
    {
        "leaf_id": "L2",
        "title": "Section 2",
        "finding_ids": ["F2", "F3"],
        "findings": [
            {"finding_id": "F2", "statement": "The notice period is 30 days.", "citation": "C2"},
            {"finding_id": "F3", "statement": "Ravi Sharma is the Lessee.", "citation": "C3"},
        ],
    },
]

FINDINGS_FOR_DOCUMENT = [
    {"finding_id": f"F{i}", "statement": s, "citation": f"CITE-{i}"}
    for i, s in enumerate(
        [
            "The device measures 12 kg.",
            "The sample was logged on 2 March.",
            "Priya Nair approved the batch.",
            "The shipment cleared customs on 5 April.",
            "The warehouse holds 300 units.",
        ]
    )
]


def check_prompt_identity() -> list[dict]:
    """The exact pre-contract formula every fidelity measurement (EXP-048
    onward) was taken against: instruction + blank line + source lines.
    """
    rows = []
    for leaf in LEAVES_FOR_PROMPT_CHECK:
        prompt, src_text, _cite_ids = build_prompt(leaf, {})
        lines = []
        for finding in leaf["findings"]:
            cite = finding.get("citation") or finding.get("evidence_id")
            lines.append(f"{finding['statement']} [{cite}]")
        expected_src = "\n".join(lines)
        expected_instruction = (
            "Rewrite the single verified fact below as one grammatically correct sentence. "
            "Do not remove it, shorten it, or leave it blank. Do not add any fact, name, number, "
            "or date not listed below. Keep the citation marker exactly as written, in square "
            "brackets."
            if len(leaf["findings"]) == 1
            else "Combine these verified facts into one flowing paragraph. Do not drop any of them. "
            "Do not add any fact, name, number, or date not listed below. Keep every citation "
            "marker exactly as written, in square brackets."
        )
        expected_prompt = expected_instruction + "\n\n" + expected_src
        rows.append({"leaf_id": leaf["leaf_id"], "identical": prompt == expected_prompt, "src_identical": src_text == expected_src})
    return rows


def check_document_writer() -> dict:
    assembled = assemble(FINDINGS_FOR_DOCUMENT, task="lookup", glossary={})
    outline = build_outline(FINDINGS_FOR_DOCUMENT, task="lookup")
    out_path = Path(__file__).resolve().parents[2] / "data" / "exp_074_document_contract" / "sample_document.md"
    doc_result = write_document("Sample Report", assembled, FINDINGS_FOR_DOCUMENT, "lookup", out_path)

    file_text = out_path.read_text(encoding="utf-8")
    doc_markers = set(citation_markers(assembled["document"]))
    file_markers = set(citation_markers(file_text))

    return {
        "doc_result": doc_result,
        "leaves": len(outline),
        "toc_entries_match_leaves": doc_result["sections"] == len(outline),
        "citation_index_exact": file_markers == doc_markers and doc_result["citations_indexed"] == len(doc_markers),
        "file_exists": out_path.exists(),
        "file_contains_title": "# Sample Report" in file_text,
        "file_contains_toc_header": "## Table of Contents" in file_text,
    }


def main():
    run = Run("EXP-074", "exp_074_document_contract")

    prompt_rows = check_prompt_identity()
    doc_check = check_document_writer()
    run.write_json("items.json", {"prompt_identity": prompt_rows, "document_writer": doc_check})

    prompt_all_identical = all(r["identical"] and r["src_identical"] for r in prompt_rows)
    doc_all_correct = doc_check["toc_entries_match_leaves"] and doc_check["citation_index_exact"] and doc_check["file_exists"] and doc_check["file_contains_title"] and doc_check["file_contains_toc_header"]

    metrics = {
        "prompt_contract": {"n": len(prompt_rows), "all_identical": prompt_all_identical, "rows": prompt_rows},
        "document_writer": doc_check,
    }

    prose = (
        f"Prompt contract migration: {'byte-identical' if prompt_all_identical else 'DIVERGED'} to the "
        f"pre-contract prompt text on {len(prompt_rows)} sample leaves (1-fact and 2-fact). Document writer: "
        f"table of contents has {doc_check['doc_result']['sections']} entries for {doc_check['leaves']} leaves "
        f"({'match' if doc_check['toc_entries_match_leaves'] else 'MISMATCH'}); citation index "
        f"{'exactly matches' if doc_check['citation_index_exact'] else 'does NOT match'} the markers actually "
        f"present in the assembled document; file written to {doc_check['doc_result']['path']}."
    )

    conclusion = (
        (
            "The mandatory prompt contract (lab.common.prompt_contract) is now the one shared way every "
            "generative call site builds a prompt, and migrating the existing rewriter role onto it changed "
            "nothing about what gets sent to the model -- confirmed by direct string equality, not assumed from "
            "the refactor being 'just a wrapper'. The document-assembly capstone (lab.common.document_writer) "
            "writes one complete, correctly-structured file: a table of contents with exactly as many entries "
            "as there are leaves, and a citation index that exactly matches what the assembled body actually "
            "cites -- every structural fact still decided by Python, nothing by a model."
            if prompt_all_identical and doc_all_correct
            else "At least one check failed -- see metrics for specifics, not smoothed over."
        )
    )

    run.finish(
        title="Mandatory prompt contract (no text change) and the document-assembly capstone",
        goal=(
            "Prove lab.common.real_rewriter's migration onto lab.common.prompt_contract is byte-identical to "
            "the prompt text every fidelity measurement since EXP-048 was taken against, and prove "
            "lab.common.document_writer produces a correctly structured, complete document file from "
            "lab.common.assemble's existing output."
        ),
        method=(
            "Prompt identity: rebuild the pre-contract prompt formula by hand for a 1-fact and a 2-fact leaf, "
            "compare by direct string equality against lab.common.real_rewriter.build_prompt's actual output "
            "(now routed through the contract). Document writer: assemble() 5 findings into 2 leaves, write "
            "the result to a file, check the table of contents' entry count against the real leaf count and "
            "the citation index against the citation markers lab.common.verify.citation_markers finds in the "
            "assembled body."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="2 prompt samples, 1 document sample (5 findings, 2 leaves) -- enough to prove both contracts hold, not a broad document-formatting test.",
        referenced_files=FILES,
        follow_ups=[
            "document_writer only emits Markdown; a .docx or PDF target would need its own writer behind the same assembled-dict input, not a different contract.",
            "The no-context fallback (lab.common.open_domain, EXP-072) does not yet route its prompt through labeled=True in a measured way beyond a smoke check -- worth its own identity-style check once that path is exercised more.",
        ],
        models_used="None -- both checks are pure string/file comparisons, no model loaded.",
    )


if __name__ == "__main__":
    main()
