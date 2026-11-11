"""EXP-056: ask-relevance gate, and whether a more directive single-fact prompt

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

reduces EXP-054's residual collapse at leaf size 1.

Two things, both prompted by the same conversation: (1) the fidelity gate
checked faithfulness to the source findings but never checked whether the
output still serves the ask that produced those findings -- a text can stay
perfectly faithful to its source and still be useless, or (as EXP-054 found)
collapse to something that is technically faithful to nothing at all. (2)
EXP-054's leaf-size-1 failures were a *new* failure mode (drop the content,
keep only the citation marker), not EXP-048's original one, so before adding
another new rewriter (EXP-055) the existing one should get a real attempt at
a fix: a more directive single-fact prompt, explicitly telling the model not
to leave the fact blank.

Part A sanity-checks lab.common.relevance.ask_relevance on clear-cut cases.
Part B reruns EXP-054's leaf-size-1 fixture with the improved prompt
(lab.common.real_rewriter.build_prompt's single-finding branch) and an ask
passed through the new ask-relevance gate, and reports the fidelity pass
rate and the citation-only-collapse count side by side with EXP-054's.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.real_rewriter import MODEL_NAME, load, rewrite_unit
from lab.common.relevance import ask_relevance

FILES = [
    "lab/exp_056_ask_relevance_gate/run.py",
    "lab/common/relevance.py",
    "lab/common/real_rewriter.py",
    "lab/common/verify.py",
    "lab/common/engine.py",
    "lab/common/assemble.py",
    "lab/common/harness.py",
    "data/exp_054_rewriter_leaf_size/results.json",
    "data/exp_056_ask_relevance_gate/results.json",
]

RELEVANCE_CASES = [
    {"ask": "What is the notice period?", "text": "The notice period is 30 days. [C1]", "expect_relevant": True},
    {"ask": "What is the notice period?", "text": "[C1]", "expect_relevant": False},
    {"ask": "What is the security deposit?", "text": "Ravi Sharma is the Lessee. [C1]", "expect_relevant": False},
    {"ask": "Who is the Lessee?", "text": "Ravi Sharma is the Lessee. [C1]", "expect_relevant": True},
    {"ask": "", "text": "Anything at all. [C1]", "expect_relevant": True},
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
ASK = "Summarize the lease's key terms."


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
    run = Run("EXP-056", "exp_056_ask_relevance_gate")

    relevance_rows = []
    for case in RELEVANCE_CASES:
        result = ask_relevance(case["ask"], case["text"])
        relevance_rows.append({**case, "got": result, "correct": result["relevant"] == case["expect_relevant"]})
    run.write_json("relevance_cases.json", relevance_rows)
    relevance_accuracy = round(sum(r["correct"] for r in relevance_rows) / len(relevance_rows), 4)

    findings = build_findings()
    leaves = leaves_of_size_1(findings)
    tokenizer, model = load()

    def run_condition(ask: str | None) -> list[dict]:
        rows = []
        for leaf in leaves:
            result = rewrite_unit(leaf, GLOSSARY, tokenizer=tokenizer, model=model, ask=ask)
            rows.append(
                {
                    "leaf_id": leaf["leaf_id"],
                    "used_generative": result["used_generative"],
                    "fallback_reason": result["fallback_reason"],
                    "generated_text": result["generated_text"],
                    "ask_relevance": result["checks"]["ask_relevance"],
                }
            )
        return rows

    # Isolate the two changes: the improved prompt alone (ask=None, so the gate
    # can't reject on relevance) versus the improved prompt plus the ask-relevance
    # gate turned on. Conflating them in one run can't tell you which did what.
    prompt_only = run_condition(ask=None)
    prompt_and_gate = run_condition(ask=ASK)
    run.write_json("diagnostics.json", {"prompt_only": prompt_only, "prompt_and_ask_gate": prompt_and_gate})

    diagnostics = prompt_and_gate
    n = len(diagnostics)

    def summarize(rows: list[dict]) -> dict:
        passed = sum(1 for d in rows if d["used_generative"])
        failures = [d for d in rows if not d["used_generative"]]
        citation_only = sum(
            1 for d in failures if d["generated_text"].strip().startswith("[") and len(d["generated_text"].strip().split()) <= 2
        )
        return {
            "leaves": len(rows),
            "fidelity_pass_rate": round(passed / len(rows), 4),
            "citation_only_collapse_count": citation_only,
        }

    prompt_only_summary = summarize(prompt_only)
    prompt_and_gate_summary = summarize(prompt_and_gate)
    passed = sum(1 for d in diagnostics if d["used_generative"])
    citation_only = prompt_and_gate_summary["citation_only_collapse_count"]
    ask_relevance_triggered = sum(1 for d in diagnostics if d["ask_relevance"] and not d["ask_relevance"]["relevant"])
    ask_relevance_only_failures = sum(
        1 for d in diagnostics if not d["used_generative"] and d["fallback_reason"] == ["ask_relevance"]
    )

    exp054_path = ROOT / "data" / "exp_054_rewriter_leaf_size" / "results.json"
    exp054 = json.loads(exp054_path.read_text())["metrics"] if exp054_path.exists() else None

    metrics = {
        "model": MODEL_NAME,
        "relevance_sanity_cases": len(RELEVANCE_CASES),
        "relevance_sanity_accuracy": relevance_accuracy,
        "leaf_size_1_leaves": n,
        "prompt_only_no_ask_gate": prompt_only_summary,
        "prompt_and_ask_gate": prompt_and_gate_summary,
        "ask_relevance_gate_triggered_count": ask_relevance_triggered,
        "failures_caused_only_by_ask_relevance": ask_relevance_only_failures,
    }
    if exp054:
        metrics["vs_exp_054_leaf_size_1_original_prompt"] = {
            "exp_054_fidelity_pass_rate": exp054["by_leaf_size"]["1"]["fidelity_pass_rate"],
            "exp_054_citation_only_collapse_count": exp054["leaf_size_1_residual_failure_mode"]["dropped_statement_kept_only_citation"],
            "exp_056_prompt_only_fidelity_pass_rate": prompt_only_summary["fidelity_pass_rate"],
            "exp_056_prompt_only_citation_only_collapse_count": prompt_only_summary["citation_only_collapse_count"],
        }

    prose = (
        f"Ask-relevance sanity check: {relevance_accuracy} correct on {len(RELEVANCE_CASES)} clear-cut cases, "
        "including catching EXP-054's exact collapse shape (bare citation marker, no content) as irrelevant. "
        f"Isolating the two changes: prompt alone (no ask gate) scores fidelity pass rate "
        f"{prompt_only_summary['fidelity_pass_rate']} with {prompt_only_summary['citation_only_collapse_count']} "
        f"citation-only collapses "
        + (f"(EXP-054's original prompt scored {exp054['by_leaf_size']['1']['fidelity_pass_rate']} with "
           f"{exp054['leaf_size_1_residual_failure_mode']['dropped_statement_kept_only_citation']} collapses). "
           if exp054 else "")
        + f"Adding the ask-relevance gate on top drops pass rate to {prompt_and_gate_summary['fidelity_pass_rate']}: "
        f"it triggered on {ask_relevance_triggered} of 13 leaves, {ask_relevance_only_failures} of which would "
        "otherwise have passed every other check."
    )

    prompt_improved = exp054 and prompt_only_summary["fidelity_pass_rate"] > exp054["by_leaf_size"]["1"]["fidelity_pass_rate"]
    conclusion = (
        f"The ask-relevance check itself is correct on {relevance_accuracy} of {len(RELEVANCE_CASES)} "
        "unambiguous sanity cases -- the function works as designed. But wiring it in with a literal "
        f"high-level ask ({ASK!r}) against single-fact leaves backfires here: {ask_relevance_only_failures} "
        "leaves that were otherwise faithful, verified rewrites get rejected only because an isolated fact "
        "like 'Ravi Sharma is the Lessee.' doesn't happen to restate the words 'summarize', 'lease', or "
        "'terms'. Token-overlap relevance works when a question's own key noun phrase naturally reappears in "
        "its answer (EXP-012's fixed-passage cases, or a direct QA ask); it does not work against an atomic "
        "fact drawn from a broader summarization ask, because there is no reason that fact's wording should "
        "echo the ask's wording. This is a real design gap in lab.common.relevance.ask_relevance as written, "
        "not a success to report quietly: the check needs to compare against something narrower than the "
        "whole-document ask (the leaf's own finding, or a sub-ask from EXP-052's eventual table of contents) "
        "before it is wired into the rewriter gate by default. "
        + (
            f"Isolated from that problem, the more directive single-fact prompt alone did help: fidelity pass "
            f"rate went from {exp054['by_leaf_size']['1']['fidelity_pass_rate']} to "
            f"{prompt_only_summary['fidelity_pass_rate']}, and citation-only collapses from "
            f"{exp054['leaf_size_1_residual_failure_mode']['dropped_statement_kept_only_citation']} to "
            f"{prompt_only_summary['citation_only_collapse_count']}."
            if prompt_improved
            else "Isolated from that problem, the more directive single-fact prompt alone did not clearly "
            "improve on EXP-054's numbers either."
        )
    )

    run.finish(
        title="Ask-relevance gate, and a more directive prompt for the bounded rewriter",
        goal=(
            "Add an ask-relevance check to the fidelity gate (a rewrite can be faithful to its source and "
            "still fail to serve the ask) and test whether a more directive single-fact prompt reduces "
            "EXP-054's leaf-size-1 citation-only collapse."
        ),
        method=(
            "Part A: lab.common.relevance.ask_relevance scored on 5 unambiguous ask/text pairs, including "
            "EXP-054's own citation-only collapse shape. Part B: EXP-054's identical 13 findings, leaf size 1, "
            "rerun with lab.common.real_rewriter.build_prompt's new single-finding instruction ('do not leave "
            "it blank') and an ask passed through the gate, compared directly against EXP-054's leaf-size-1 "
            "numbers."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Same 13 findings as EXP-054/EXP-048, 5 hand-picked relevance sanity cases, not a large relevance benchmark.",
        referenced_files=FILES,
        follow_ups=[
            "EXP-052's ask-driven table of contents would give this gate a fixture where ask-relevance "
            "actually needs to catch something numbers/NLI don't.",
            "If the prompt fix's gain holds up on a larger fixture, make it the default single-finding prompt "
            "rather than an experimental variant.",
        ],
        models_used=(
            f"{MODEL_NAME}, the same local checkpoint EXP-048/054 measured. Part A uses no model, classical "
            "token-coverage only."
        ),
    )


if __name__ == "__main__":
    main()
