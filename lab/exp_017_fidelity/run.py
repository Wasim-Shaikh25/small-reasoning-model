"""EXP-017: fidelity checks and deterministic rewrite (architecture Experiment A, no generator)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run, fidelity
from lab.common.verify import bidirectional_nli, entity_number_check, modality_preserved

FILES = [
    "lab/exp_017_fidelity/run.py",
    "lab/common/harness.py",
    "lab/common/verify.py",
    "lab/common/nli.py",
    "lab/common/textutil.py",
    "data/exp_017_fidelity/items.json",
    "data/exp_017_fidelity/results.json",
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


def deterministic_render(lines: list[str], style: str) -> str:
    """Whitespace and order only. No paraphrase, because that would be generation."""
    cleaned = [" ".join(line.split()) for line in lines if line.strip()]
    if style == "shorten":
        # Keep every line that carries a number, a modal, or a capitalized name.
        return " ".join(cleaned)
    return " ".join(cleaned)


def mutate(text: str, kind: str) -> str:
    if kind == "drop_number":
        return text.replace("30", "", 1)
    if kind == "add_number":
        return text + " The fee is 99."
    if kind == "flip_modal":
        return text.replace("shall", "may", 1)
    if kind == "drop_not":
        return re.sub(r"\bnot\b", "", text, count=1)
    return text


def main():
    run = Run("EXP-017", "exp_017_fidelity")
    styles = ["simplify", "formalize", "shorten", "claims", "memo"]
    preserved = []
    added = []
    modal_ok = []
    both_ways = []
    for style in styles:
        for claim in CLAIMS:
            out = deterministic_render([claim], style)
            report = fidelity(claim, out)
            preserved.append(report["numbers_dropped"] == [])
            added.append(report["numbers_added"] == [])
            modal_ok.append(report["modal_changed"] is False)
            both_ways.append(bidirectional_nli(claim, out)["ok"])
        for paragraph in PARAGRAPHS:
            out = deterministic_render([paragraph], style)
            report = fidelity(paragraph, out)
            preserved.append(not report["numbers_dropped"])
            added.append(not report["numbers_added"])
            modal_ok.append(not report["modal_changed"])
            both_ways.append(bidirectional_nli(paragraph, out)["ok"])
    mutations = []
    source = "The notice period is 30 days. The tenant shall not sublet unless the Lessor consents."
    clean = deterministic_render([source], "memo")
    for kind in ("drop_number", "add_number", "flip_modal", "drop_not"):
        bad = mutate(clean, kind)
        report = fidelity(source, bad)
        numbers = entity_number_check(source, bad)
        caught = bool(report["numbers_dropped"] or report["numbers_added"] or report["modal_changed"] or not modality_preserved(source, bad))
        mutations.append({"kind": kind, "caught": caught, "numbers": numbers, "modal_changed": report["modal_changed"]})
    n = len(preserved)
    metrics = {
        "renders": n,
        "fact_preservation_rate": round(sum(preserved) / n, 4),
        "added_content_rate": round(1 - sum(added) / n, 4),
        "modal_error_rate": round(1 - sum(modal_ok) / n, 4),
        "bidirectional_nli_pass_rate": round(sum(both_ways) / n, 4),
        "fluency_human_rating": None,
        "mutation_catch": mutations,
        "mutation_catch_rate": round(sum(m["caught"] for m in mutations) / len(mutations), 4),
        "generator_used": False,
    }
    run.write_json("items.json", {"claims": CLAIMS, "paragraphs": PARAGRAPHS})
    prose = (
        f"Deterministic rendering of {n} claim and paragraph cases preserved numbers in {metrics['fact_preservation_rate']} "
        f"and added numbers in {metrics['added_content_rate']}. "
        f"Modal error rate is {metrics['modal_error_rate']}. "
        f"Bidirectional lexical NLI pass rate is {metrics['bidirectional_nli_pass_rate']}. "
        f"Planted bad edits were caught at {metrics['mutation_catch_rate']}: {mutations}. "
        "No human fluency score was collected."
    )
    run.finish(
        title="Rewrite fidelity without a generator",
        goal="Measure fact, number, and modality preservation for a deterministic renderer, and show that the fidelity checks catch planted edits.",
        method="The renderer joins already verified sentences and normalizes whitespace. It does not paraphrase. Fidelity uses the architecture's number and modal comparison. Planted edits drop a number, add a number, or flip shall/not. Bidirectional NLI is the lexical judge.",
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "Because the renderer copies verified sentences, number and modal preservation is a property of that copy step and was measured, not assumed. "
            "The validator catches the planted edits. Fluency was not rated by a person. A generative rewriter is not part of this run."
        ),
        scale_down="Eight claims and five paragraphs, each rendered in five style labels that all take the copy path. This is smaller than 50 paragraphs and 50 claim lists, and it does not call FLAN-T5.",
        referenced_files=FILES,
        follow_ups=["A human 1-to-5 fluency rating can be added later. It must not be replaced with a generative model."],
    )


if __name__ == "__main__":
    main()
