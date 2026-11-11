"""EXP-062: does telling the model exactly what it dropped, then letting it

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

retry, fix EXP-054's residual citation-only collapse?

EXP-054 measured flan-t5-small at leaf size 1 (one fact per call, the
narrowest possible scope): fidelity pass rate 0.3846, and every one of the 8
remaining failures was the same shape -- the model generated nothing but the
citation marker, dropping the fact's content entirely. A more directive
prompt alone (EXP-056) did not fix this.

This tests a different kind of control: instead of asking the model to try
harder in general, tell it exactly what its own last output was missing
(lab.common.real_rewriter._missing_feedback) and let it regenerate, up to 2
additional attempts, before falling back to the deterministic text. If this
closes the gap, the model could hold the fact all along and simply was not
told clearly enough what it missed. If it does not, that is evidence the
failure is more structural than a missing nudge -- supporting the research
report's recommendation that the real fix is training-data-level (fine-tune
on fusion-shaped data), not prompt-level.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.real_rewriter import MODEL_NAME, load, rewrite_unit

FILES = [
    "lab/exp_062_retry_with_feedback/run.py",
    "lab/common/real_rewriter.py",
    "lab/common/assemble.py",
    "lab/common/harness.py",
    "data/exp_054_rewriter_leaf_size/results.json",
    "data/exp_056_ask_relevance_gate/results.json",
    "data/exp_062_retry_with_feedback/results.json",
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
MAX_RETRIES = 2


def build_findings() -> list[dict]:
    rows = []
    for i, claim in enumerate(CLAIMS):
        rows.append({"finding_id": f"CL{i:03d}", "statement": claim, "citation": f"CITE-CL{i:03d}", "evidence_id": f"CITE-CL{i:03d}"})
    for i, paragraph in enumerate(PARAGRAPHS):
        rows.append({"finding_id": f"PG{i:03d}", "statement": paragraph, "citation": f"CITE-PG{i:03d}", "evidence_id": f"CITE-PG{i:03d}"})
    return rows


def leaves_of_size_1(findings: list[dict]) -> list[dict]:
    return [
        {"leaf_id": f"L{i:04d}", "title": f"Section {i + 1}", "finding_ids": [f["finding_id"]], "findings": [f]}
        for i, f in enumerate(findings)
    ]


def main():
    run = Run("EXP-062", "exp_062_retry_with_feedback")
    findings = build_findings()
    leaves = leaves_of_size_1(findings)
    tokenizer, model = load()

    diagnostics = []
    total_generate_calls = 0
    for leaf in leaves:
        result = rewrite_unit(leaf, GLOSSARY, tokenizer=tokenizer, model=model, max_retries=MAX_RETRIES)
        total_generate_calls += len(result["attempts"])
        diagnostics.append(
            {
                "leaf_id": leaf["leaf_id"],
                "used_generative": result["used_generative"],
                "attempts_made": len(result["attempts"]),
                "fixed_by_retry": result["used_generative"] and len(result["attempts"]) > 1,
                "attempt_outcomes": [a["ok"] for a in result["attempts"]],
                "final_generated": result["generated_text"],
            }
        )
    run.write_json("diagnostics.json", diagnostics)

    n = len(diagnostics)
    passed = sum(1 for d in diagnostics if d["used_generative"])
    fixed_by_retry = sum(1 for d in diagnostics if d["fixed_by_retry"])
    failed_even_with_retries = [d for d in diagnostics if not d["used_generative"]]

    metrics = {
        "model": MODEL_NAME,
        "max_retries": MAX_RETRIES,
        "leaves": n,
        "fidelity_pass_rate_with_retry": round(passed / n, 4),
        "fixed_by_retry_count": fixed_by_retry,
        "total_generate_calls": total_generate_calls,
        "calls_per_leaf_avg": round(total_generate_calls / n, 2),
        "still_failing_after_all_retries": len(failed_even_with_retries),
        "exp_054_baseline_no_retry_pass_rate": 0.3846,
        "exp_054_baseline_citation_only_collapses": 8,
    }

    prose = (
        f"With up to {MAX_RETRIES} retries and explicit 'you dropped X' feedback, fidelity pass rate is "
        f"{metrics['fidelity_pass_rate_with_retry']} (EXP-054's no-retry baseline on the identical fixture: "
        f"0.3846). Retries fixed {fixed_by_retry} of the leaves that failed on the first attempt. "
        f"Total generate() calls: {total_generate_calls} across {n} leaves ({metrics['calls_per_leaf_avg']}/leaf), "
        f"versus 1/leaf with no retry. {len(failed_even_with_retries)} leaves still fail even after every retry."
    )

    improved = metrics["fidelity_pass_rate_with_retry"] > 0.3846
    conclusion = (
        f"Explicit 'you dropped X, include it' feedback "
        + (
            f"measurably helps: pass rate rises from 0.3846 to {metrics['fidelity_pass_rate_with_retry']}, "
            f"fixing {fixed_by_retry} leaves that failed on the first attempt alone. This means the model "
            "could hold the fact some of the time -- it was not told clearly enough what its own output "
            "missed, not structurally incapable of the task on those leaves. That is a meaningfully "
            "different finding from EXP-054's, and a cheap, dependency-free control mechanism worth keeping "
            "as a first line of defense before falling back to the deterministic text."
            if improved
            else "does not meaningfully close the gap EXP-054 measured. This is evidence the failure is more "
            "structural than a missing nudge: telling the model exactly what it dropped and asking it to "
            "retry does not reliably make it include that content. This supports the research report's "
            "recommendation over a prompt-level fix -- the next lever to pull is training-data-level "
            "(fine-tuning on fusion-shaped data with guaranteed content coverage), not further prompt "
            "engineering."
        )
        + f" The retry loop costs {metrics['calls_per_leaf_avg']}x the inference calls of the no-retry path "
        f"for whatever gain it provides -- a real cost to weigh against the alternative of just running "
        "the deterministic fallback immediately, which is free."
    )

    run.finish(
        title="Retry with explicit missing-content feedback vs. EXP-054's no-retry baseline",
        goal=(
            "Test whether telling flan-t5-small exactly what its previous attempt dropped, then letting it "
            "retry up to 2 more times, closes the citation-only-collapse gap EXP-054 measured at leaf size 1 "
            "-- a cheap, dependency-free control mechanism to test before investing in harder fixes "
            "(constrained decoding, fine-tuning)."
        ),
        method=(
            "Identical 13 findings and leaf size 1 as EXP-054/056. lab.common.real_rewriter.rewrite_unit's "
            "new max_retries parameter: on a failed fidelity check, build feedback naming exactly which "
            "numbers/citations were dropped (lab.common.real_rewriter._missing_feedback) and append it to "
            "the original prompt, regenerate, up to 2 additional attempts, before falling back to the "
            "deterministic text -- the same fallback behavior as every other closed rewriter exploration."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Same 13 findings as EXP-054/056, 2 retries, not a sweep over retry count or feedback phrasing.",
        referenced_files=FILES,
        follow_ups=[
            "If this helps, test whether 1 retry captures most of the gain (cheaper) or more retries keep "
            "helping (diminishing returns curve not yet measured).",
            "If this doesn't help, the research report's fine-tuning recommendation is the next concrete "
            "step: build a small DiscoFuse-style synthetic 'combine facts, keep all of them' dataset and "
            "LoRA-adapt flan-t5-small on it.",
        ],
        models_used=(
            f"{MODEL_NAME}, the same local checkpoint EXP-048/054/056 measured. The retry loop is new "
            "control flow around the same checkpoint and the same fidelity gate, not a different model or "
            "a change to the gate's own criteria."
        ),
    )


if __name__ == "__main__":
    main()
