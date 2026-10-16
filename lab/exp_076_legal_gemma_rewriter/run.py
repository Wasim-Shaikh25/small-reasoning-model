"""EXP-076: a community legal/financial fine-tune of gemma3:270m, measured
on the identical fixture every other bounded-rewriter exploration used --
not trusted from its own model card's self-reported perplexity numbers.

FORBIDDEN.md's third bounded-rewriter checkpoint, permitted 2026-10-16:
`nagbhaskar55/gemma-3-270m-bhaskar-finetune`, someone else's already-
completed fine-tune of gemma3:270m on 7,617 synthetic legal/financial
examples (1,560 of them explicitly "rewriting"). Added to test the project
owner's question directly: is training-distribution style match -- not
more epochs or a higher LoRA rank, EXP-073's own finding -- what multi-
fact-leaf synthesis needed, using someone else's larger-scale fine-tune
rather than retraining ourselves again.

Same 13 findings, same two leaf sizes (1 and 4) as EXP-048/054/056/062/063/
064, run through lab.common.rewriter_backends.rewrite_unit -- the model-
agnostic path, proving that path works for a brand new checkpoint with
zero changes to build_prompt, fidelity_gate, or rewrite_unit's shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.real_rewriter_legal_gemma import MODEL_NAME, model_card
from lab.common.rewriter_backends import rewrite_unit

FILES = [
    "lab/exp_076_legal_gemma_rewriter/run.py",
    "lab/common/real_rewriter_legal_gemma.py",
    "lab/common/rewriter_backends.py",
    "FORBIDDEN.md",
    "lab/config/models.json",
    "data/exp_048_bounded_rewriter/results.json",
    "data/exp_063_gemma3_rewriter/results.json",
    "data/exp_064_constrained_decoding/results.json",
    "data/exp_076_legal_gemma_rewriter/results.json",
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
CHECKPOINT = MODEL_NAME


def build_findings() -> list[dict]:
    rows = []
    for i, claim in enumerate(CLAIMS):
        rows.append({"finding_id": f"CL{i:03d}", "statement": claim, "citation": f"CITE-CL{i:03d}"})
    for i, paragraph in enumerate(PARAGRAPHS):
        rows.append({"finding_id": f"PG{i:03d}", "statement": paragraph, "citation": f"CITE-PG{i:03d}"})
    return rows


def leaves_of_size_1(findings: list[dict]) -> list[dict]:
    return [{"leaf_id": f"L{i:04d}", "title": f"Section {i + 1}", "finding_ids": [f["finding_id"]], "findings": [f]} for i, f in enumerate(findings)]


def leaf_of_size_4(findings: list[dict]) -> dict:
    chunk = findings[:4]
    return {"leaf_id": "L_4FACT", "title": "Section 1", "finding_ids": [f["finding_id"] for f in chunk], "findings": chunk}


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
    run = Run("EXP-076", "exp_076_legal_gemma_rewriter")
    findings = build_findings()
    leaves = leaves_of_size_1(findings)

    leaf1_rows = []
    for leaf in leaves:
        result = rewrite_unit(leaf, GLOSSARY, checkpoint=CHECKPOINT)
        leaf1_rows.append({"leaf_id": leaf["leaf_id"], "used_generative": result["used_generative"], "fallback_reason": result["fallback_reason"], "generated_text": result["generated_text"]})

    multi_leaf = leaf_of_size_4(findings)
    multi_result = rewrite_unit(multi_leaf, GLOSSARY, checkpoint=CHECKPOINT)
    multi_row = {
        "leaf_id": multi_leaf["leaf_id"],
        "findings_in_leaf": len(multi_leaf["findings"]),
        "used_generative": multi_result["used_generative"],
        "fallback_reason": multi_result["fallback_reason"],
        "generated_text": multi_result["generated_text"],
    }
    run.write_json("items.json", {"leaf_size_1": leaf1_rows, "leaf_size_4": multi_row})

    summary = summarize(leaf1_rows)
    metrics = {
        "model": CHECKPOINT,
        "model_card": model_card(),
        "leaf_size_1": summary,
        "leaf_size_4_passed": multi_row["used_generative"],
        "leaf_size_4_fail_reasons": multi_row["fallback_reason"],
        "comparison_flan_t5_small_leaf_size_1": 0.3846,
        "comparison_gemma3_270m_ollama_raw_leaf_size_1": 0.0,
        "comparison_gemma3_270m_ollama_spliced_leaf_size_1": 0.8462,
        "comparison_gemma3_270m_ollama_constrained_leaf_size_1": 1.0,
    }

    missing_citation_only = summary["fail_reason_counts"].get("citations", 0) > 0 and summary["fail_reason_counts"].get("numbers", 0) == 0

    prose = (
        f"Leaf size 1 (13 findings, raw, no splice/constraint repair): fidelity pass rate {summary['fidelity_pass_rate']}. "
        f"Fail reasons: {summary['fail_reason_counts']}. Leaf size 4 (the original hard case): "
        f"{'passed' if multi_row['used_generative'] else 'failed, reasons ' + str(multi_row['fallback_reason'])}. "
        f"For comparison on the identical fixture: flan-t5-small {metrics['comparison_flan_t5_small_leaf_size_1']}, "
        f"gemma3:270m via Ollama raw {metrics['comparison_gemma3_270m_ollama_raw_leaf_size_1']} "
        f"(spliced {metrics['comparison_gemma3_270m_ollama_spliced_leaf_size_1']}, decoding-constrained "
        f"{metrics['comparison_gemma3_270m_ollama_constrained_leaf_size_1']})."
    )

    conclusion = (
        (
            "This checkpoint's failure mode on the standard fixture is the same shape as vanilla gemma3:270m's "
            "(EXP-063): content is preserved faithfully, but the citation marker is consistently dropped, not a "
            "content-fidelity failure. The same post-hoc splice (EXP-063) or decoding-level constraint (EXP-064) "
            "that fixed that checkpoint's identical gap is the natural next step here too, not yet applied in "
            "this exploration -- this measures the raw, unrepaired checkpoint, same as EXP-063's first pass did."
            if missing_citation_only
            else "This checkpoint's failures are not purely a citation-formatting gap -- see fail_reason_counts; "
            "a different repair strategy would be needed, reported as measured rather than assumed to match "
            "EXP-063's pattern."
        )
        + (
            " On the original 4-fact leaf specifically, it still fails -- legal-domain training-distribution "
            "match alone did not fix multi-fact synthesis the way the project owner's hypothesis (EXP-073's "
            "finding) suggested it might, at least not without the same repair layer the single-fact case needs."
            if not multi_row["used_generative"]
            else " Notably, it passed the original 4-fact leaf raw, unlike every other checkpoint and method "
            "tried so far (EXP-048/054/056/062/064) -- a real, measured result worth treating as a genuine "
            "finding, not a fluke, before relying on it further."
        )
    )

    run.finish(
        title="A community legal/financial fine-tune of gemma3:270m, measured on the standard fixture",
        goal=(
            "Measure nagbhaskar55/gemma-3-270m-bhaskar-finetune (FORBIDDEN.md's third bounded-rewriter "
            "checkpoint, permitted 2026-10-16) on the identical 13-finding fixture and both leaf sizes every "
            "other rewriter exploration used, through the new model-agnostic rewrite_unit "
            "(lab.common.rewriter_backends) -- testing whether someone else's larger-scale legal-domain "
            "fine-tune fixes what EXP-073's own from-scratch LoRA attempt could not."
        ),
        method=(
            "Identical 13 findings (8 claims, 5 paragraphs) and leaf-size-1 split as EXP-048/054/056/062/063, "
            "plus the identical first-4-findings leaf as EXP-064, run through "
            "lab.common.rewriter_backends.rewrite_unit(checkpoint='nagbhaskar55/gemma-3-270m-bhaskar-finetune') "
            "-- raw, no post-hoc splice or decoding constraint, for a fair first measurement against the other "
            "checkpoints' own first (raw) measurements."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Same 13 findings as every other rewriter exploration, one checkpoint, raw generation only (no splice/constraint repair applied yet).",
        referenced_files=FILES,
        follow_ups=[
            "If the citation-marker gap is the only failure mode (as EXP-063's identical pattern suggests), apply the same post-hoc splice or decoding-constrained approach and remeasure.",
            "Not yet tested: whether this checkpoint's chat-template prompting (vs. the plain-string prompting flan-t5-small/gemma3:270m-via-Ollama use) itself affects fidelity independent of the checkpoint's own fine-tuning -- a confound this exploration doesn't isolate.",
        ],
        models_used=f"{MODEL_NAME} (base {model_card()['base_model']}), a third-party fine-tune, measured not trusted. Rewriter role only, same fidelity gate as every other checkpoint in this repo.",
    )


if __name__ == "__main__":
    main()
