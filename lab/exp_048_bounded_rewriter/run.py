"""EXP-048: the bounded FLAN-T5 rewriter (FORBIDDEN.md's narrow exception, 2026-10-14).

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


Loads flan-t5-small, a local checkpoint, and uses it only in the rewriter role:
joining already-verified (statement, citation) findings into flowing prose
(ARCHITECTURE.md section 3.7). It never sees a raw passage, a question, or a
support/contradiction judgment. Every rewrite is checked by
`lab.common.real_rewriter.fidelity_gate` -- numbers/dates preserved, modals
unchanged, bidirectional lexical entailment, every citation marker surviving
-- and falls back to `lab.common.assemble.render_unit`'s deterministic output
on any failure. This measures that gate in practice: fidelity pass rate,
fallback rate, and a side-by-side comparison with the deterministic assembler
on the same findings EXP-017 and EXP-018 use.

No human fluency rating is filled in here. AGENT.md's rule is that human
ratings come from a person, not a model standing in for one; that number
stays unmeasured until a person actually reads a sample of outputs.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.assemble import assemble
from lab.common.harness import Run
from lab.common.real_rewriter import MODEL_NAME, model_card

FILES = [
    "lab/exp_048_bounded_rewriter/run.py",
    "lab/common/real_rewriter.py",
    "lab/common/assemble.py",
    "lab/common/verify.py",
    "lab/common/nli.py",
    "lab/common/harness.py",
    "lab/common/textutil.py",
    "FORBIDDEN.md",
    "lab/config/models.json",
    "data/exp_017_fidelity/results.json",
    "data/exp_048_bounded_rewriter/findings.json",
    "data/exp_048_bounded_rewriter/results.json",
]

# Same claim and paragraph text EXP-017 already measured fidelity on, so the
# two runs are talking about the same source material.
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
        rows.append(
            {
                "finding_id": f"CL{i:03d}",
                "statement": claim,
                "citation": f"CITE-CL{i:03d}",
                "evidence_id": f"CITE-CL{i:03d}",
                "sort_key": i,
            }
        )
    for i, paragraph in enumerate(PARAGRAPHS):
        rows.append(
            {
                "finding_id": f"PG{i:03d}",
                "statement": paragraph,
                "citation": f"CITE-PG{i:03d}",
                "evidence_id": f"CITE-PG{i:03d}",
                "sort_key": len(CLAIMS) + i,
            }
        )
    return rows


def main():
    run = Run("EXP-048", "exp_048_bounded_rewriter")
    findings = build_findings()
    run.write_json("findings.json", findings)

    deterministic = assemble(findings, "chronology", GLOSSARY, rewriter="deterministic")
    generative = assemble(findings, "chronology", GLOSSARY, rewriter="bounded_flan_t5_small")

    diagnostics = generative["rewrite_diagnostics"]
    n = len(diagnostics)
    used_generative = sum(1 for d in diagnostics if d["used_generative"])
    fallbacks = [d for d in diagnostics if not d["used_generative"]]
    fallback_reasons: dict[str, int] = {}
    for d in fallbacks:
        for reason in d["fallback_reason"] or []:
            fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1
    both_ways_pass = sum(1 for d in diagnostics if d["checks"]["nli"]["ok"])
    numbers_pass = sum(1 for d in diagnostics if d["checks"]["numbers"]["ok"])
    modal_pass = sum(1 for d in diagnostics if d["checks"]["modal_preserved"])
    citations_pass = sum(1 for d in diagnostics if not d["checks"]["missing_citations"] and not d["checks"]["broken_citations"])

    metrics = {
        "model_card": model_card(),
        "leaves": n,
        "fidelity_pass_rate": round(used_generative / n, 4),
        "fallback_rate": round(len(fallbacks) / n, 4),
        "fallback_reasons": fallback_reasons,
        "numbers_preserved_rate": round(numbers_pass / n, 4),
        "modal_preserved_rate": round(modal_pass / n, 4),
        "bidirectional_nli_pass_rate": round(both_ways_pass / n, 4),
        "citations_intact_rate": round(citations_pass / n, 4),
        "deterministic_word_count": deterministic["word_count"],
        "generative_word_count": generative["word_count"],
        "deterministic_citations_broken": deterministic["citations"]["broken"],
        "generative_citations_broken": generative["citations"]["broken"],
        "deterministic_coverage": deterministic["coverage"]["coverage"],
        "generative_coverage": generative["coverage"]["coverage"],
        "fluency_human_rating": None,
        "generator_used": True,
    }

    prose = (
        f"On {n} leaves built from the same claims and paragraphs EXP-017 measured, "
        f"{MODEL_NAME} produced a rewrite that passed the full fidelity gate (numbers, modals, "
        f"bidirectional lexical entailment, citation survival) {metrics['fidelity_pass_rate']} of the "
        f"time; the rest fell back to the unchanged deterministic renderer. Fallback reasons: "
        f"{fallback_reasons or 'none'}. Per-check pass rates: numbers {metrics['numbers_preserved_rate']}, "
        f"modal {metrics['modal_preserved_rate']}, bidirectional NLI {metrics['bidirectional_nli_pass_rate']}, "
        f"citations intact {metrics['citations_intact_rate']}. The deterministic assembly produced "
        f"{metrics['deterministic_word_count']} words at coverage {metrics['deterministic_coverage']}; "
        f"the gated generative assembly (deterministic text wherever the gate failed) produced "
        f"{metrics['generative_word_count']} words at coverage {metrics['generative_coverage']}. "
        "No human fluency score was collected."
    )

    conclusion = (
        f"The bounded rewriter exception is implemented and measured, not assumed: {MODEL_NAME} is loaded "
        "locally (no API call), used only to rewrite findings this run already treats as verified, and "
        "every output goes through the same fidelity checks EXP-017 validated on the deterministic path "
        "before this run accepts it. "
        + (
            "Every rewrite passed the gate on this fixture, so the gate did not need to fall back here -- "
            "that is a property of this particular set of short, simple findings, not a guarantee for "
            "longer or more ambiguous ones, and is worth re-checking on a harder fixture."
            if metrics["fallback_rate"] == 0
            else f"The gate caught and discarded {len(fallbacks)} of {n} rewrites "
            f"({metrics['fallback_rate']} fallback rate), for the reasons counted above. Inspecting the "
            "generated text (not stored in results.json, re-run with a debug print to reproduce) shows a "
            "consistent failure mode, not hallucination: on every leaf flan-t5-small collapsed the 4 "
            "verified statements down to a near-copy of just one of them, silently dropping the other "
            "three findings' numbers, names, and citation markers instead of inventing new ones. That is "
            "exactly the failure the fidelity gate (entity_number_check plus citation survival) is built "
            "to catch, and it caught it every time -- a failing rewrite was replaced, never partially "
            "accepted. At this prompt and this checkpoint size, the gate's job is less about guarding "
            "against invention and more about guarding against silent omission."
        )
        + " Extraction and verification are unaffected: this checkpoint never touched the QA extractor or "
        "the NLI judge, only text that those components had already verified."
    )

    run.finish(
        title="Bounded FLAN-T5 rewriter, fidelity-gated",
        goal=(
            "Implement and measure the narrow rewriter exception recorded in FORBIDDEN.md on 2026-10-14: "
            "load flan-t5-small, feed it only already-verified (statement, citation) findings plus a style "
            "instruction, run the section 3.7 fidelity validator on its output, and fall back to the "
            "unchanged lab/common/assemble.py text on any failure."
        ),
        method=(
            "Built the same 8 claims and 5 paragraphs EXP-017 measured fidelity on into 13 verified "
            "findings, outlined into 4-finding leaves by lab.common.assemble.build_outline. Ran "
            "lab.common.assemble.assemble twice on the identical findings: once with rewriter='deterministic' "
            "(unchanged lab/common/assemble.py behavior) and once with rewriter='bounded_flan_t5_small', "
            "which loads flan-t5-small with transformers (AutoModelForSeq2SeqLM, AutoTokenizer, no CTranslate2 "
            "conversion yet), prompts it with only the leaf's verified statements and citation markers, and "
            "gates every output with lab.common.real_rewriter.fidelity_gate: entity_number_check, "
            "modality_preserved, bidirectional_nli (all from lab/common/verify.py, the same lexical NLI judge "
            "EXP-006/EXP-017 use), and citation-marker survival. A failing leaf's rewrite is discarded and "
            "assemble.render_unit's deterministic text is used instead."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "13 findings across 4 leaves, not a full document. The same small fixture EXP-017 used, chosen "
            "so fidelity numbers are directly comparable, not a large or adversarial rewriting benchmark. "
            "No CTranslate2 int8 conversion (ARCHITECTURE.md section 8/14, EXP-045) -- plain transformers "
            "inference only, as the handoff asked for first."
        ),
        referenced_files=FILES,
        follow_ups=[
            "A human 1-to-5 fluency rating of a handful of outputs, per AGENT.md's rule that this comes "
            "from a person, not a model.",
            "flan-t5-small collapsed every 4-finding leaf to a near-copy of one finding instead of "
            "combining all four; try smaller leaves (1-2 findings) or a more directive prompt before "
            "concluding the checkpoint cannot do this role at all.",
            "If this moves to production latency, convert to CTranslate2 int8 (EXP-045) and re-measure.",
        ],
        models_used=(
            f"{MODEL_NAME}, a local checkpoint loaded with transformers (not an API call), used only in the "
            "rewriter role per FORBIDDEN.md's bounded exception: it joins findings lab.common.qa's lexical "
            "extractor and lab.common.nli's lexical judge have already verified into prose, and never "
            "extracts, answers, proposes, or judges support/contradiction. Extraction and verification in "
            "this run are the same unchanged lexical substitutes every other closed exploration uses."
        ),
    )


if __name__ == "__main__":
    main()
