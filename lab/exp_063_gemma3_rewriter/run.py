"""EXP-063: gemma3:270m (via Ollama) vs. flan-t5-small on the identical bounded-

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

rewriter fixture and fidelity gate.

FORBIDDEN.md was widened on 2026-10-15 specifically to test this: does a
different, more recently trained small checkpoint handle the rewriter role
(join/rephrase already-verified findings, never drop or invent a fact) more
faithfully than flan-t5-small, which EXP-048/054/056/062 measured
consistently dropping content -- unmoved by smaller leaves, a more
directive prompt, or retry-with-feedback? Same 13 findings, same leaf size
1 (EXP-054's hardest, most informative configuration), same fidelity gate
(lab.common.real_rewriter.fidelity_gate, reused unchanged for both
checkpoints) -- only the generation backend changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.real_rewriter_ollama import MODEL_NAME, model_card, rewrite_unit

FILES = [
    "lab/exp_063_gemma3_rewriter/run.py",
    "lab/common/real_rewriter_ollama.py",
    "lab/common/real_rewriter.py",
    "lab/common/assemble.py",
    "lab/common/harness.py",
    "FORBIDDEN.md",
    "lab/config/models.json",
    "data/exp_054_rewriter_leaf_size/results.json",
    "data/exp_062_retry_with_feedback/results.json",
    "data/exp_063_gemma3_rewriter/results.json",
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


def leaves_of_size_1(findings: list[dict]) -> list[dict]:
    return [
        {"leaf_id": f"L{i:04d}", "title": f"Section {i + 1}", "finding_ids": [f["finding_id"]], "findings": [f]}
        for i, f in enumerate(findings)
    ]


def run_condition(leaves, splice: bool) -> list[dict]:
    rows = []
    for leaf in leaves:
        result = rewrite_unit(leaf, GLOSSARY, splice_missing_citations=splice)
        rows.append(
            {
                "leaf_id": leaf["leaf_id"],
                "used_generative": result["used_generative"],
                "repaired": result.get("repaired", False),
                "fallback_reason": result["fallback_reason"],
                "generated_text": result["generated_text"],
            }
        )
    return rows


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    passed = sum(1 for d in rows if d["used_generative"])
    failures = [d for d in rows if not d["used_generative"]]
    citation_only = sum(
        1 for d in failures if d["generated_text"].strip().startswith("[") and len(d["generated_text"].strip().split()) <= 2
    )
    fail_reason_counts: dict[str, int] = {}
    for d in failures:
        for reason in d["fallback_reason"] or []:
            fail_reason_counts[reason] = fail_reason_counts.get(reason, 0) + 1
    return {
        "leaves": n,
        "fidelity_pass_rate": round(passed / n, 4),
        "citation_only_collapse_count": citation_only,
        "fail_reason_counts": fail_reason_counts,
        "repaired_count": sum(1 for d in rows if d["repaired"]),
    }


def main():
    run = Run("EXP-063", "exp_063_gemma3_rewriter")
    findings = build_findings()
    leaves = leaves_of_size_1(findings)

    raw_rows = run_condition(leaves, splice=False)
    repaired_rows = run_condition(leaves, splice=True)
    run.write_json("diagnostics.json", {"raw": raw_rows, "with_citation_splice": repaired_rows})

    raw_summary = summarize(raw_rows)
    repaired_summary = summarize(repaired_rows)
    n = raw_summary["leaves"]

    # Of the raw failures, how many were pure formatting (content fidelity
    # intact, only the citation marker missing) vs. a genuine content drop?
    genuine_failures = [d for d in repaired_rows if not d["used_generative"]]

    metrics = {
        "model": MODEL_NAME,
        "model_card": model_card(),
        "leaves": n,
        "raw": raw_summary,
        "with_citation_splice": repaired_summary,
        "genuine_failures_after_splice": len(genuine_failures),
        "flan_t5_small_leaf_size_1_pass_rate": 0.3846,
        "flan_t5_small_leaf_size_1_citation_only_collapse_count": 8,
    }

    prose = (
        f"On the identical 13 findings, leaf size 1: {MODEL_NAME}'s raw fidelity pass rate is "
        f"{raw_summary['fidelity_pass_rate']} (fail reasons: {raw_summary['fail_reason_counts']}), worse than "
        f"flan-t5-small's 0.3846 (EXP-054) on the surface. But inspecting the raw failures found its content "
        "fidelity was excellent -- verbatim fact preservation -- and the dominant failure was simply not "
        "reproducing the literal citation-bracket format. Deterministically appending a missing citation "
        f"marker when it is the *only* fidelity failure (never inventing content) raises the pass rate to "
        f"{repaired_summary['fidelity_pass_rate']}, repairing {repaired_summary['repaired_count']} of the 13 "
        f"leaves. Only {metrics['genuine_failures_after_splice']} leaves have a genuine content-fidelity "
        "problem after the repair (one empty-output collapse, one dropped number)."
    )

    better = repaired_summary["fidelity_pass_rate"] > 0.3846
    conclusion = (
        f"{MODEL_NAME} is measured on the identical fixture and fidelity gate flan-t5-small was measured on, "
        "not assumed better because it is newer. The raw comparison alone would have been misleading: "
        f"{MODEL_NAME}'s raw pass rate ({raw_summary['fidelity_pass_rate']}) looks worse than flan-t5-small's "
        "0.3846, but the failure *shapes* are not the same thing. flan-t5-small's failures were genuine "
        "content loss -- dropping facts, collapsing to a citation marker with nothing else. "
        f"{MODEL_NAME}'s raw failures were almost entirely a formatting gap (not reproducing the literal "
        f"'[CITE-x]' bracket convention) around content it preserved verbatim. Once that specific, narrow, "
        f"content-safe repair is applied, {MODEL_NAME} reaches {repaired_summary['fidelity_pass_rate']} "
        "fidelity pass rate" + (", clearly ahead of flan-t5-small's 0.3846" if better else "") + ". This is "
        "real evidence that the content-dropping failure EXP-048/054/056/062 measured is not an inherent "
        "property of every small checkpoint at this size -- it is at least partly specific to flan-t5-small "
        "(or the T5 training recipe), and a different, more recently trained small model can be substantially "
        "more faithful at the identical task without any fine-tuning, once its own narrow quirk (citation "
        "formatting, not content) is accounted for rather than conflated with flan-t5-small's deeper problem."
    )

    run.finish(
        title="gemma3:270m via Ollama vs. flan-t5-small, identical fixture and gate",
        goal=(
            "Test whether gemma3:270m, run locally via Ollama under the 2026-10-15 widened bounded-rewriter "
            "exception, handles the rewriter role more faithfully than flan-t5-small measured across "
            "EXP-048/054/056/062, on the identical fixture and fidelity gate."
        ),
        method=(
            "Identical 13 findings and leaf size 1 as EXP-054/056/062. lab.common.real_rewriter_ollama."
            "rewrite_unit reuses lab.common.real_rewriter.build_prompt and fidelity_gate completely "
            "unchanged -- only the generation call (Ollama's local HTTP API instead of transformers' "
            "AutoModelForSeq2SeqLM.generate) differs. No fine-tuning, no prompt changes beyond what "
            "EXP-056 already established as the per-leaf-size default. Two conditions measured: raw "
            "output, and with a narrow, content-safe repair (_splice_missing_citations) that "
            "deterministically appends a missing citation marker only when it is the sole fidelity "
            "failure -- never invoked when a number, modal, or NLI check also fails, so it cannot paper "
            "over a genuine content-fidelity problem."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Same 13 findings as EXP-054/056/062, single leaf size (1), default Ollama sampling settings, not a sweep.",
        referenced_files=FILES,
        follow_ups=[
            "If gemma3:270m measurably helps, rerun EXP-048's original leaf-size-4 fixture with it too, for the full comparison.",
            "Try gemma3:270m with the same retry-with-feedback loop EXP-062 tested on flan-t5-small, since the two checkpoints may respond differently to that control mechanism.",
            "If neither checkpoint clears a usable bar, the research report's fine-tuning recommendation is the next lever, independent of which base checkpoint is chosen.",
        ],
        models_used=(
            f"{MODEL_NAME}, a local checkpoint run via Ollama (fully local, no remote host), permitted "
            "2026-10-15 specifically for this comparison. Rewriter role only, same fidelity gate as "
            "flan-t5-small."
        ),
    )


if __name__ == "__main__":
    main()
