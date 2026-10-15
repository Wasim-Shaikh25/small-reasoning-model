"""EXP-064: real decoding-level constraints for gemma3:270m, not a post-hoc patch.

EXP-063 found gemma3:270m preserves content verbatim but drops the citation
marker, and fixed 11 of 13 cases with a post-hoc splice (append the missing
marker, then re-check). This tests the stronger version: can the citation
and non-emptiness be made structurally impossible to violate, via Ollama's
JSON-schema structured-output support (llama.cpp grammar-constrained
sampling under the hood) -- found reachable after discovering that true
token-level constrained decoding via transformers was blocked behind an
untrusted remote-code package, and that Ollama's HTTP API gives no raw logit
access to build a custom beam search loop ourselves. The schema constraint
is a different, real mechanism, not a workaround: the model cannot decode a
citation other than the required one, and cannot decode an empty rewrite,
because the grammar forbids both.

Same 13 findings, same leaf size 1, same fidelity gate as EXP-054/056/062/063.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.real_rewriter_ollama import MODEL_NAME, model_card, rewrite_unit, rewrite_unit_constrained

FILES = [
    "lab/exp_064_constrained_decoding/run.py",
    "lab/common/real_rewriter_ollama.py",
    "lab/common/real_rewriter.py",
    "lab/common/harness.py",
    "FORBIDDEN.md",
    "data/exp_063_gemma3_rewriter/results.json",
    "data/exp_064_constrained_decoding/results.json",
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


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    passed = sum(1 for d in rows if d["used_generative"])
    fail_reason_counts: dict[str, int] = {}
    for d in rows:
        if not d["used_generative"]:
            for reason in d["fallback_reason"] or []:
                fail_reason_counts[reason] = fail_reason_counts.get(reason, 0) + 1
    return {"leaves": n, "fidelity_pass_rate": round(passed / n, 4), "fail_reason_counts": fail_reason_counts}


def main():
    run = Run("EXP-064", "exp_064_constrained_decoding")
    findings = build_findings()
    leaves = leaves_of_size_1(findings)

    splice_rows = []
    constrained_rows = []
    for leaf in leaves:
        splice_result = rewrite_unit(leaf, GLOSSARY, splice_missing_citations=True)
        splice_rows.append({"leaf_id": leaf["leaf_id"], "used_generative": splice_result["used_generative"], "fallback_reason": splice_result["fallback_reason"], "generated_text": splice_result["generated_text"]})

        constrained_result = rewrite_unit_constrained(leaf, GLOSSARY)
        constrained_rows.append({"leaf_id": leaf["leaf_id"], "used_generative": constrained_result["used_generative"], "fallback_reason": constrained_result["fallback_reason"], "generated_text": constrained_result["generated_text"]})

    run.write_json("diagnostics.json", {"post_hoc_splice": splice_rows, "decoding_constrained": constrained_rows})

    splice_summary = summarize(splice_rows)
    constrained_summary = summarize(constrained_rows)

    metrics = {
        "model": MODEL_NAME,
        "model_card": model_card(),
        "post_hoc_splice": splice_summary,
        "decoding_constrained": constrained_summary,
        "exp_063_splice_baseline_pass_rate": 0.8462,
        "flan_t5_small_pass_rate": 0.3846,
    }

    prose = (
        f"Post-hoc splice (EXP-063's method, rerun here for a same-run comparison): {splice_summary['fidelity_pass_rate']} "
        f"fidelity pass rate. Decoding-level constraint (this exploration's method, citation and non-emptiness "
        f"enforced by the JSON schema, not repaired after the fact): {constrained_summary['fidelity_pass_rate']}. "
        f"Fail reasons under the constrained method: {constrained_summary['fail_reason_counts']}."
    )

    better = constrained_summary["fidelity_pass_rate"] > splice_summary["fidelity_pass_rate"]
    conclusion = (
        f"Real decoding-level constraints, reached through Ollama's JSON-schema structured-output support "
        "rather than the blocked transformers constrained-beam-search path or an untrusted remote-code "
        "package, "
        + (
            f"improve on the post-hoc splice: {constrained_summary['fidelity_pass_rate']} versus "
            f"{splice_summary['fidelity_pass_rate']}. The citation can no longer be dropped by construction, "
            "and an empty rewrite is no longer decodable at all -- both are now grammar-level impossibilities, "
            "not failures caught and patched afterward. Remaining failures are free-text content problems "
            "(e.g. a dropped number) that a JSON-schema constraint on a single enum field cannot reach -- "
            "the fidelity gate is still required for those, and still does its job."
            if better
            else "does not clearly improve on the post-hoc splice on this fixture -- the splice already "
            "captured most of the achievable gain for this specific failure mode (missing citation, "
            "otherwise-faithful content), and the harder constraint doesn't reach the different failure "
            "modes (empty output, dropped numbers) any more effectively than catching them post-hoc."
        )
    )

    run.finish(
        title="Decoding-level constraints vs. post-hoc splice for gemma3:270m",
        goal=(
            "Test whether forcing the citation marker and a non-empty rewrite at the decoding level "
            "(Ollama's JSON-schema structured output, llama.cpp grammar-constrained sampling) improves on "
            "EXP-063's post-hoc splice repair, on the identical fixture and fidelity gate."
        ),
        method=(
            "Identical 13 findings, leaf size 1. lab.common.real_rewriter_ollama.rewrite_unit_constrained "
            "requests a JSON object with a 'rewritten_sentence' field (minLength 1, so an empty decode is "
            "not valid under the grammar) and a 'citations' field (enum-constrained to the exact required "
            "citation ids) instead of free-text generation, then runs the same "
            "lab.common.real_rewriter.fidelity_gate used by every other rewriter exploration. Compared "
            "directly against rewrite_unit's post-hoc splice path in the same run."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Same 13 findings as EXP-054/056/062/063, single leaf size, one schema design, not a sweep over constraint strategies.",
        referenced_files=FILES,
        follow_ups=[
            "Extend the schema to also require restating each number as a separate enum-constrained field, "
            "to see if the remaining number-drop failure can be constrained away the same way citations were.",
            "Measure latency/overhead of structured-output decoding versus free-text generation, since "
            "grammar-constrained sampling is not free.",
        ],
        models_used=(
            f"{MODEL_NAME}, the same local Ollama checkpoint EXP-063 measured. Rewriter role only, same "
            "fidelity gate, same fallback -- only the decoding mechanism for this comparison's second "
            "condition differs."
        ),
    )


if __name__ == "__main__":
    main()
