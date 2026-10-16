"""EXP-073: does an offline LoRA adapter fix multi-fact-leaf synthesis,
where every non-training approach tried so far (EXP-048/054/056/062/064)
did not?

FORBIDDEN.md's narrow offline LoRA fine-tuning exception, recorded
2026-10-16. Trains a LoRA adapter on flan-t5-small -- not gemma3:270m,
which is gate-restricted on HuggingFace and this environment has no
credentials that accepted its license; flan-t5-small already has the
identical failure measured on it, so this tests the same question -- on
deterministically-generated synthetic DiscoFuse-style data
(lab.common.synthetic_fusion_data): "combine these 2-4 facts into one
sentence, keep every one and every citation."

Scaled down hard for CPU-only training in this environment (no GPU): a
small train/eval split, few epochs, low LoRA rank. This is a first,
honestly-scaled measurement, not a tuned production recipe -- said plainly
in scale_down, not hidden.

The one comparison that actually matters: baseline (unmodified) vs.
LoRA-adapted flan-t5-small on the *original* EXP-048/064 4-fact leaf, the
real failure this whole investigation started from, not just a fresh
synthetic eval split the adapter might have gotten lucky on.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.lora_finetune import examples_to_pairs, load_lora, train_lora
from lab.common.real_rewriter import MODEL_NAME, _generate, build_prompt, fidelity_gate, load
from lab.common.synthetic_fusion_data import generate_dataset

FILES = [
    "lab/exp_073_lora_fine_tune/run.py",
    "lab/common/lora_finetune.py",
    "lab/common/synthetic_fusion_data.py",
    "lab/common/real_rewriter.py",
    "FORBIDDEN.md",
    "lab/config/models.json",
    "data/exp_048_bounded_rewriter/results.json",
    "data/exp_064_constrained_decoding/results.json",
    "data/exp_073_lora_fine_tune/results.json",
]

ADAPTER_DIR = ROOT / "data" / "exp_073_lora_fine_tune" / "adapter"

# The original EXP-048/064 4-fact leaf -- the real failure, not a fresh
# synthetic case the adapter might get right by chance.
ORIGINAL_CLAIMS = [
    "The notice period is 30 days.",
    "The security deposit is INR 50000.",
    "Ravi Sharma is the Lessee.",
    "The lease was signed on 5 January 2024.",
]


def build_original_4fact_leaf() -> dict:
    findings = [
        {"finding_id": f"CL{i:03d}", "statement": claim, "citation": f"CITE-CL{i:03d}"}
        for i, claim in enumerate(ORIGINAL_CLAIMS)
    ]
    return {"leaf_id": "L_ORIG_4FACT", "title": "Section 1", "finding_ids": [f["finding_id"] for f in findings], "findings": findings}


def evaluate_leaf(leaf: dict, tokenizer, model, glossary: dict | None = None) -> dict:
    glossary = glossary or {}
    prompt, src_text, cite_ids = build_prompt(leaf, glossary)
    generated = _generate(tokenizer, model, prompt, max_new_tokens=160)
    checks = fidelity_gate(src_text, generated, cite_ids)
    return {"leaf_id": leaf["leaf_id"], "generated": generated, "ok": checks["ok"], "fail_reasons": checks["fail_reasons"]}


def main():
    run = Run("EXP-073", "exp_073_lora_fine_tune")

    train_examples = generate_dataset(n_examples=60, seed=1, min_facts=2, max_facts=4)
    eval_examples = generate_dataset(n_examples=15, seed=2, min_facts=2, max_facts=4)
    train_pairs = examples_to_pairs(train_examples)

    train_result = train_lora(train_pairs, ADAPTER_DIR, rank=8, epochs=2, batch_size=4)
    run.write_json("train_result.json", train_result)

    base_tokenizer, base_model = load()
    lora_tokenizer, lora_model = load_lora(ADAPTER_DIR)

    original_leaf = build_original_4fact_leaf()
    base_original = evaluate_leaf(original_leaf, base_tokenizer, base_model)
    lora_original = evaluate_leaf(original_leaf, lora_tokenizer, lora_model)

    base_eval_rows = [evaluate_leaf(ex, base_tokenizer, base_model) for ex in eval_examples]
    lora_eval_rows = [evaluate_leaf(ex, lora_tokenizer, lora_model) for ex in eval_examples]
    run.write_json(
        "items.json",
        {"base_original_4fact": base_original, "lora_original_4fact": lora_original, "base_eval": base_eval_rows, "lora_eval": lora_eval_rows},
    )

    base_eval_pass = sum(r["ok"] for r in base_eval_rows)
    lora_eval_pass = sum(r["ok"] for r in lora_eval_rows)

    metrics = {
        "train_result": train_result,
        "original_4fact_leaf": {"base_ok": base_original["ok"], "lora_ok": lora_original["ok"], "base_fail_reasons": base_original["fail_reasons"], "lora_fail_reasons": lora_original["fail_reasons"]},
        "held_out_synthetic_eval": {
            "n": len(eval_examples),
            "base_pass_rate": round(base_eval_pass / len(eval_examples), 4),
            "lora_pass_rate": round(lora_eval_pass / len(eval_examples), 4),
        },
    }

    prose = (
        f"On the original EXP-048/064 4-fact leaf: base flan-t5-small {'passed' if base_original['ok'] else 'failed, reasons ' + str(base_original['fail_reasons'])}; "
        f"LoRA-adapted {'passed' if lora_original['ok'] else 'failed, reasons ' + str(lora_original['fail_reasons'])}. "
        f"On {len(eval_examples)} held-out synthetic eval leaves: base pass rate {metrics['held_out_synthetic_eval']['base_pass_rate']}, "
        f"LoRA pass rate {metrics['held_out_synthetic_eval']['lora_pass_rate']}."
    )

    fixed_original = (not base_original["ok"]) and lora_original["ok"]
    improved_eval = metrics["held_out_synthetic_eval"]["lora_pass_rate"] > metrics["held_out_synthetic_eval"]["base_pass_rate"]

    conclusion = (
        (
            "The LoRA adapter fixes the exact original failure (EXP-048/064's 4-fact leaf), which no "
            "non-training approach tried so far (leaf decomposition alone wasn't an option here since this "
            "leaf is deliberately 4 facts; retry-with-feedback, decoding constraints) could fix. "
            if fixed_original
            else "The LoRA adapter did NOT fix the original 4-fact leaf failure -- reported as measured, not "
            "assumed away. "
        )
        + (
            f"It also improved the held-out synthetic pass rate ({metrics['held_out_synthetic_eval']['base_pass_rate']} -> "
            f"{metrics['held_out_synthetic_eval']['lora_pass_rate']}), suggesting the gain generalizes beyond one "
            "memorized example, not just the training distribution it was shown. "
            if improved_eval
            else f"It did NOT improve the held-out synthetic pass rate ({metrics['held_out_synthetic_eval']['base_pass_rate']} -> "
            f"{metrics['held_out_synthetic_eval']['lora_pass_rate']}) -- "
            + ("even though it fixed the one original case, that could be memorization of a near-duplicate pattern rather than a generalized skill, worth treating with caution. " if fixed_original else "consistent with the original case also failing. ")
        )
        + "This training run is scaled down hard for CPU-only execution (60 train examples, 2 epochs, LoRA "
        "rank 8) -- a first measurement of whether the mechanism works at all, not a tuned production recipe."
    )

    run.finish(
        title="Offline LoRA fine-tuning of flan-t5-small for multi-fact-leaf synthesis",
        goal=(
            "Test FORBIDDEN.md's new offline LoRA exception on the one problem nothing else fixed: "
            "multi-fact-leaf synthesis, measured against the actual original EXP-048/064 failure case, not "
            "just a fresh synthetic benchmark."
        ),
        method=(
            "60 synthetic train examples + 15 held-out synthetic eval examples (lab.common.synthetic_fusion_data, "
            "deterministically generated, 2-4 facts each). LoRA adapter (rank 8, q/v projections) trained 2 "
            "epochs via peft+transformers on flan-t5-small's frozen base weights. Evaluated via the identical "
            "fidelity_gate every other rewriter exploration uses, both on the held-out synthetic set and on "
            "the original EXP-048/064 4-fact leaf (notice period / deposit / Lessee / lease date), base vs. "
            "LoRA-adapted, same prompt, same decoding."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "CPU-only (no GPU in this environment), so train set (60), epochs (2), and LoRA rank (8) are all "
            "small by fine-tuning standards -- a first measurement of mechanism, not a tuned recipe. "
            "flan-t5-small substituted for gemma3:270m (gate-restricted on HuggingFace, no accepted credentials "
            "here) -- see FORBIDDEN.md/lab/config/models.json for why this still tests the same question."
        ),
        referenced_files=FILES,
        follow_ups=[
            "Retry with gemma3:270m if HF license access to it is ever obtained, to see if the same recipe transfers.",
            "If this helped, sweep train-set size and epochs (still CPU-bound) before concluding the scaled-down numbers are near a ceiling.",
            "The adapter is saved under data/exp_073_lora_fine_tune/adapter but not wired into lab.common.assemble's rewriter modes yet -- that wiring is a separate, deliberate step, not assumed here.",
        ],
        models_used=f"{MODEL_NAME} base + a LoRA adapter trained in this exploration (FORBIDDEN.md's offline LoRA fine-tuning exception, 2026-10-16). Rewriter role only.",
    )


if __name__ == "__main__":
    main()
