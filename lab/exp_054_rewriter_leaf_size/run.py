"""EXP-054: does narrowing the task size prevent the bounded rewriter's collapse?

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


EXP-048 measured flan-t5-small collapsing every 4-finding leaf to a near-
copy of one finding, dropping the other three's numbers and citations --
fidelity pass rate 0.0. That is the general failure this project's design
philosophy predicts: a small model is not weak at language, it is weak at
holding more than a little at once, so the fix is not a bigger model, it is
narrowing what any one call is asked to do until the job fits what a small
model can actually get right -- then fall back on anything it still
misses. This exploration tests that hypothesis directly: same checkpoint,
same fixture as EXP-048, only the leaf size changes (1, 2, 4 findings per
rewrite call), and fidelity pass rate is the dependent variable.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.real_rewriter import MODEL_NAME, load, rewrite_unit

FILES = [
    "lab/exp_054_rewriter_leaf_size/run.py",
    "lab/common/real_rewriter.py",
    "lab/common/assemble.py",
    "lab/common/harness.py",
    "data/exp_048_bounded_rewriter/results.json",
    "data/exp_054_rewriter_leaf_size/results.json",
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
        rows.append({"finding_id": f"CL{i:03d}", "statement": claim, "citation": f"CITE-CL{i:03d}", "evidence_id": f"CITE-CL{i:03d}"})
    for i, paragraph in enumerate(PARAGRAPHS):
        rows.append({"finding_id": f"PG{i:03d}", "statement": paragraph, "citation": f"CITE-PG{i:03d}", "evidence_id": f"CITE-PG{i:03d}"})
    return rows


def leaves_of_size(findings: list[dict], size: int) -> list[dict]:
    leaves = []
    for i in range(0, len(findings), size):
        chunk = findings[i : i + size]
        leaves.append(
            {
                "leaf_id": f"L{i:04d}",
                "title": f"Section {i // size + 1}",
                "finding_ids": [f["finding_id"] for f in chunk],
                "findings": chunk,
            }
        )
    return leaves


def main():
    run = Run("EXP-054", "exp_054_rewriter_leaf_size")
    findings = build_findings()
    tokenizer, model = load()

    by_size = {}
    all_rows = []
    for size in (1, 2, 4):
        leaves = leaves_of_size(findings, size)
        diagnostics = []
        for leaf in leaves:
            result = rewrite_unit(leaf, GLOSSARY, tokenizer=tokenizer, model=model)
            diagnostics.append(
                {
                    "leaf_id": leaf["leaf_id"],
                    "leaf_size": size,
                    "findings_in_leaf": len(leaf["findings"]),
                    "used_generative": result["used_generative"],
                    "fallback_reason": result["fallback_reason"],
                    "generated_text": result["generated_text"],
                }
            )
        all_rows.extend(diagnostics)
        n = len(diagnostics)
        passed = sum(1 for d in diagnostics if d["used_generative"])
        by_size[str(size)] = {
            "leaves": n,
            "fidelity_pass_rate": round(passed / n, 4),
            "fallback_rate": round((n - passed) / n, 4),
        }
    run.write_json("diagnostics.json", all_rows)

    metrics = {
        "model": MODEL_NAME,
        "by_leaf_size": by_size,
        "exp_048_leaf_size_4_fidelity_pass_rate": 0.0,
    }

    prose = (
        f"Fidelity pass rate by leaf size on the identical 13 findings EXP-048 used: "
        + ", ".join(f"{size} finding(s)/leaf -> {stats['fidelity_pass_rate']}" for size, stats in by_size.items())
        + "."
    )

    size1_failures = [d for d in all_rows if d["leaf_size"] == 1 and not d["used_generative"]]
    empty_except_citation = sum(1 for d in size1_failures if d["generated_text"].strip().startswith("[") and len(d["generated_text"].strip().split()) <= 2)
    metrics["leaf_size_1_residual_failure_mode"] = {
        "failures": len(size1_failures),
        "dropped_statement_kept_only_citation": empty_except_citation,
    }

    improves_with_smaller_leaves = by_size["1"]["fidelity_pass_rate"] > by_size["4"]["fidelity_pass_rate"]
    conclusion = (
        f"{MODEL_NAME} is measured at leaf sizes 1, 2, and 4 findings per rewrite call, isolating leaf size "
        "as the only variable changed from EXP-048. "
        + (
            "Narrowing the task to one finding per call raises the fidelity pass rate from 0.0 to "
            f"{by_size['1']['fidelity_pass_rate']}, supporting this project's governing hypothesis that a "
            "small model's failure mode is being asked to hold too much at once, not a general inability to "
            "rewrite a single verified statement. But decomposition alone does not fully fix it here: "
            f"{len(size1_failures)} of 13 single-finding leaves still fail, and "
            f"{empty_except_citation} of those fail in a different, more extreme way than EXP-048's -- "
            "instead of picking one fact out of several and dropping the rest, the model sometimes drops the "
            "statement's content entirely and echoes only the citation marker (for example generating "
            "'[CITE-CL000]' with no text). Decomposition shrinks the failure, it does not remove the need for "
            "the fidelity gate -- the gate stays the load-bearing safeguard at every leaf size measured."
            if improves_with_smaller_leaves
            else "Narrowing the task to one finding per call does not raise the fidelity pass rate on this "
            "fixture. That means EXP-048's collapse was not simply a matter of leaf size for this checkpoint "
            "and this prompt; the fidelity gate (not leaf-size tuning) remains the load-bearing safeguard, "
            "and a different prompt or a different checkpoint would need to be tried before concluding "
            "decomposition alone fixes it."
        )
    )

    run.finish(
        title="Does narrowing the rewriter's task size prevent EXP-048's collapse?",
        goal=(
            "Test whether EXP-048's fidelity failure (flan-t5-small collapsing 4 findings to a near-copy of "
            "1) is a leaf-size problem -- i.e. whether bounding the model to fewer findings per call raises "
            "the fidelity pass rate, as this project's decomposition-over-capacity design principle predicts."
        ),
        method=(
            "Identical checkpoint, fixture, and fidelity gate as EXP-048 (same 13 claims/paragraphs, same "
            "lab.common.real_rewriter.rewrite_unit). The only variable changed is how many findings are "
            "grouped into each leaf before one rewrite call: 1, 2, or 4 (EXP-048's original grouping)."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Same 13 findings as EXP-048, not a larger fixture; three leaf sizes, not a full sweep.",
        referenced_files=FILES,
        follow_ups=[
            "If this closes the gap, wire the leaf size down for the bounded rewriter in "
            "lab/common/assemble.assemble() (currently hardcoded to 4 in build_outline) and re-run EXP-048 "
            "at the new size as the real default.",
            "If it does not close the gap, try a more directive single-fact prompt before concluding the "
            "checkpoint cannot do this role at this size.",
        ],
        models_used=(
            f"{MODEL_NAME}, the same local checkpoint EXP-048 measured. Rewriter role only, fidelity-gated, "
            "identical to EXP-048's contract."
        ),
    )


if __name__ == "__main__":
    main()
