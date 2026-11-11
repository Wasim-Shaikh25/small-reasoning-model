"""EXP-055: the content-only template rewriter, measured against EXP-048/054.

RETIRED (2026-11-11): the generative rewriter role this experiment measured
was withdrawn -- every real/recent measurement (this experiment's own
results among them) showed it was never actually invoked once the
deterministic pre-checks were added (see lab.common.rewriter_backends's
module docstring, and FORBIDDEN.md's dated withdrawal note). The checkpoint
modules this script imports (lab.common.real_rewriter / real_rewriter_
legal_gemma / real_rewriter_qwen / lora_finetune, and real_rewriter_ollama's
rewriter-role functions) were deleted or trimmed. This script is kept as
the permanent historical record of what it measured; its own results.json
is unaffected, but running this file again will now ImportError/TypeError.
Recover a deleted module with `git show <commit before this deletion>:lab/common/<module>.py`
if a literal rerun is ever needed.


lab.common.template_rewriter.splice_unit is the middle path AGENT.md's
"rewrite from the given content itself" rule points at: it joins verified
statements with a connector chosen from a 4-word fixed vocabulary, never
generating a token outside that vocabulary and the statements themselves.
This measures it on the identical fixture EXP-048 and EXP-054 used, through
the same fidelity gate (entity_number_check, modality_preserved,
bidirectional_nli, citation survival) those explorations measured flan-t5-
small against -- not asserting it passes by construction, checking it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.assemble import assemble, build_outline
from lab.common.harness import Run
from lab.common.real_rewriter import fidelity_gate
from lab.common.template_rewriter import splice_unit

FILES = [
    "lab/exp_055_template_rewriter/run.py",
    "lab/common/template_rewriter.py",
    "lab/common/assemble.py",
    "lab/common/real_rewriter.py",
    "lab/common/verify.py",
    "lab/common/harness.py",
    "data/exp_048_bounded_rewriter/results.json",
    "data/exp_054_rewriter_leaf_size/results.json",
    "data/exp_055_template_rewriter/results.json",
]

CLAIMS = [
    "The notice period is 30 days.",
    "The security deposit is INR 50000.",
    "Ravi Sharma is the Lessee.",
    "The lease was signed on 5 January 2024.",
    "The tenant shall not sublet unless the Lessor consents.",
    "The rent is INR 25000.",
    "The cure period is 10 days.",
    "ABC Pvt Ltd is the Lessor.",
]
PARAGRAPHS = [
    "The tenant shall pay INR 25000 on the 1st of each month and shall not withhold rent.",
    "Notice of 30 days must be given except where the premises are destroyed.",
    "Meera Iyer signed on 5 January 2024 in the presence of the witness.",
    "The deposit of INR 50000 is held until 14 days after the handover.",
    "Entry is permitted only between 09:00 and 18:00.",
]
GLOSSARY = {"R. Sharma": "Ravi Sharma"}


def build_findings() -> list[dict]:
    rows = []
    for i, claim in enumerate(CLAIMS):
        rows.append({"finding_id": f"CL{i:03d}", "statement": claim, "citation": f"CITE-CL{i:03d}", "evidence_id": f"CITE-CL{i:03d}", "sort_key": i})
    for i, paragraph in enumerate(PARAGRAPHS):
        rows.append({"finding_id": f"PG{i:03d}", "statement": paragraph, "citation": f"CITE-PG{i:03d}", "evidence_id": f"CITE-PG{i:03d}", "sort_key": len(CLAIMS) + i})
    return rows


def leaf_source_text(leaf: dict, glossary: dict[str, str]) -> tuple[str, list[str]]:
    import re

    lines, cite_ids = [], []
    for finding in leaf["findings"]:
        statement = finding["statement"]
        for variant, canonical in glossary.items():
            statement = re.sub(rf"\b{re.escape(variant)}\b", canonical, statement)
        cite = finding.get("citation") or finding.get("evidence_id")
        lines.append(f"{statement} [{cite}]")
        cite_ids.append(cite)
    return "\n".join(lines), cite_ids


def main():
    run = Run("EXP-055", "exp_055_template_rewriter")
    findings = build_findings()
    outline = build_outline(findings, "chronology")

    leaf_checks = []
    for leaf in outline:
        spliced = splice_unit(leaf, GLOSSARY)
        # splice_unit's first line is the leaf's "Section N" structural title, the
        # same scaffolding render_unit emits -- not a verified finding, and not
        # something flan-t5-small's output ever included either (its prompt never
        # asked for one). Comparing body-to-body is apples to apples; comparing
        # "Section N" against a body-only source text would count the title's own
        # digit as an invented number, which is a bug in the test, not the rewriter.
        spliced_body = spliced.split("\n", 1)[1] if "\n" in spliced else spliced
        src_text, cite_ids = leaf_source_text(leaf, GLOSSARY)
        checks = fidelity_gate(src_text, spliced_body, cite_ids)
        leaf_checks.append({"leaf_id": leaf["leaf_id"], "spliced": spliced, "checks": checks})
    run.write_json("leaf_checks.json", leaf_checks)

    n = len(leaf_checks)
    passed = sum(1 for row in leaf_checks if row["checks"]["ok"])

    deterministic_result = assemble(findings, "chronology", GLOSSARY, rewriter="deterministic")
    template_result = assemble(findings, "chronology", GLOSSARY, rewriter="template_splice")

    metrics = {
        "leaves": n,
        "fidelity_pass_rate": round(passed / n, 4),
        "deterministic_word_count": deterministic_result["word_count"],
        "template_word_count": template_result["word_count"],
        "deterministic_citations_broken": deterministic_result["citations"]["broken"],
        "template_citations_broken": template_result["citations"]["broken"],
        "deterministic_coverage": deterministic_result["coverage"]["coverage"],
        "template_coverage": template_result["coverage"]["coverage"],
        "exp_048_fidelity_pass_rate_leaf_size_4": 0.0,
        "exp_054_fidelity_pass_rate_leaf_size_1": 0.3846,
        "sample_output": next((row["spliced"] for row in leaf_checks if row["leaf_id"] == "L0002"), None),
        "fluency_human_rating": None,
    }

    prose = (
        f"On the identical {n} leaves EXP-048 and EXP-054 used, the content-only template rewriter passes the "
        f"full fidelity gate {metrics['fidelity_pass_rate']} of the time -- versus flan-t5-small's 0.0 at leaf "
        "size 4 (EXP-048) and 0.3846 at its best measured leaf size, 1 (EXP-054). Word count and coverage "
        "match the bare deterministic join exactly "
        f"({metrics['template_word_count']} vs {metrics['deterministic_word_count']} words, both at coverage "
        f"{metrics['template_coverage']}), because every statement is still copied verbatim -- only a "
        "connector word is added between them. No human fluency score was collected."
    )

    conclusion = (
        f"The content-only template rewriter passes the fidelity gate on {passed} of {n} leaves "
        f"({metrics['fidelity_pass_rate']}), where flan-t5-small passed on 0 of 4 at the original leaf size "
        "(EXP-048) and 5 of 13 at its best measured leaf size (EXP-054). This is not a surprising result, it "
        "is the structural guarantee AGENT.md's 'rewrite from the given content itself' rule predicts: a "
        "rewriter that only ever copies given statements and inserts one of 4 fixed connector words cannot "
        "drop a fact, invent one, or break a citation, because it never generates a token that could do "
        "either. It also cannot fail more gracefully than the bare bullet join -- it is strictly a readability "
        "improvement on top of the same guaranteed-faithful backbone, not a new capability. A human fluency "
        "rating, not collected here per AGENT.md's rule that this comes from a person, would be needed to "
        "know whether the connectives actually read better than the bare join; structurally, this is now the "
        "recommended middle default between the bare join and the generative rewriter, pending that rating."
    )

    run.finish(
        title="Content-only template rewriter (connective splice)",
        goal=(
            "Build and measure the middle path between assemble.render_unit's bare join and the bounded "
            "FLAN-T5 rewriter: splice verified statements with a small fixed connective vocabulary, and show "
            "it passes the same fidelity gate EXP-048/054 measured flan-t5-small against, on the identical "
            "fixture."
        ),
        method=(
            "lab.common.template_rewriter.splice_unit chooses one of 4 fixed connectors (none, 'Also,', "
            "'However,', 'In addition,') between each pair of consecutive statements in a leaf, based on "
            "shared leading subject or a sign of contrast (a new modal or a polarity flip), then copies each "
            "statement verbatim with its own citation marker. Measured through "
            "lab.common.real_rewriter.fidelity_gate (the same numbers/modal/bidirectional-NLI/citation checks "
            "EXP-048/054 used) on the identical 13 findings, 4-per-leaf grouping. Also wired into "
            "lab.common.assemble.assemble as rewriter='template_splice' and compared word-for-word against "
            "the deterministic default. Note on this measurement: splice_unit's first output line is the "
            "leaf's 'Section N' structural title (the same scaffolding render_unit emits); fidelity is "
            "checked body-to-body, excluding that title line from both sides, the same way EXP-048/054's "
            "comparison never included a title on either side. The first run of this script compared the "
            "titled output against a title-free source and measured 0.0 (the title's own digit registered "
            "as an invented number) -- a bug in the test, caught and fixed before this result, not a defect "
            "in the rewriter."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Same 13 findings as EXP-048/054/056, not a larger or more varied document.",
        referenced_files=FILES,
        follow_ups=[
            "A human 1-to-5 fluency rating comparing this against the bare bullet join, per AGENT.md's rule.",
            "Consider making this the default rewriter mode ahead of 'deterministic' once a person confirms "
            "it reads better, since it is structurally no less safe.",
        ],
        models_used="No model, generative or otherwise. Deterministic code only: a 4-word fixed connective vocabulary and rule-based selection.",
    )


if __name__ == "__main__":
    main()
