"""EXP-077: does the generative rewriter's per-leaf fidelity hold up when
chained across enough leaves to reach real document length, not just a
13-finding fixture?

The project owner's point, checked against the record rather than assumed:
EXP-018 proved the architecture scales (200/1,000/5,000 claims, up to
42,506 words) -- but entirely through the *deterministic* path, zero
sentences generated. Every generative-rewriter measurement since
(EXP-048/054/056/062/063/064/073/076) has used the same small 13-finding
fixture. Input-side scale (paged retrieval, nested navigation) has been
stress-tested up to 1,000 pages / 450 leaves. Output-side scale -- chaining
the bounded rewriter's *own* small, bounded generation step across enough
leaves to write something document-length -- has never been measured.
That gap is real, not hypothetical, confirmed against EXPLORATIONS.md
before building this, not assumed from a hunch.

This measures it directly: 80 single-fact leaves (lab.common.
synthetic_fusion_data, fresh seed, not overlapping EXP-073's train/eval
splits), each rewritten independently via gemma3:270m's decoding-
constrained path (EXP-064's measured 1.0-fidelity combination -- the best
already-proven configuration, so a failure here is about *scale*, not
about picking a weak checkpoint), then joined into one document and
checked exactly the way EXP-018 checked the deterministic path: coverage,
citation integrity, and repetition -- but now including cross-leaf
repetition, which no single-leaf fidelity check can see at all.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.assemble import citation_integrity, coverage_report, repetition_pairs
from lab.common.harness import Run
from lab.common.real_rewriter_ollama import MODEL_NAME, rewrite_unit_constrained
from lab.common.synthetic_fusion_data import generate_dataset

FILES = [
    "lab/exp_077_generation_at_scale/run.py",
    "lab/common/synthetic_fusion_data.py",
    "lab/common/real_rewriter_ollama.py",
    "lab/common/assemble.py",
    "data/exp_018_longform/results.json",
    "data/exp_064_constrained_decoding/results.json",
    "data/exp_077_generation_at_scale/results.json",
]

N_LEAVES = 80
SEED = 9001  # fresh seed, distinct from EXP-073's train (seed=1) and eval (seed=2) splits


def main():
    run = Run("EXP-077", "exp_077_generation_at_scale")

    leaves = generate_dataset(n_examples=N_LEAVES, seed=SEED, min_facts=1, max_facts=1)

    rows = []
    rendered_units = []
    t0 = time.perf_counter()
    for leaf in leaves:
        result = rewrite_unit_constrained(leaf, {})
        rows.append(
            {
                "leaf_id": leaf["leaf_id"],
                "used_generative": result["used_generative"],
                "fallback_reason": result["fallback_reason"],
                "text": result["text"],
            }
        )
        rendered_units.append(result["text"])
    elapsed = time.perf_counter() - t0
    run.write_json("items.json", rows)

    document = "\n\n".join(rendered_units)
    word_count = len(document.split())

    all_findings = [f for leaf in leaves for f in leaf["findings"]]
    valid_ids = {f["citation"] for f in all_findings}
    coverage = coverage_report(all_findings, document)
    citations = citation_integrity(document, valid_ids)
    repetition = repetition_pairs(rendered_units)

    n = len(rows)
    passed = sum(1 for r in rows if r["used_generative"])
    fail_reason_counts: dict[str, int] = {}
    for r in rows:
        if not r["used_generative"]:
            for reason in r["fallback_reason"] or []:
                fail_reason_counts[reason] = fail_reason_counts.get(reason, 0) + 1

    metrics = {
        "model": MODEL_NAME,
        "n_leaves": n,
        "fidelity_pass_rate": round(passed / n, 4),
        "fail_reason_counts": fail_reason_counts,
        "total_words_generated": word_count,
        "total_elapsed_sec": round(elapsed, 2),
        "sec_per_leaf": round(elapsed / n, 3),
        "document_level": {
            "coverage": coverage["coverage"],
            "missing_findings": coverage["missing"],
            "broken_citations": citations["broken"],
            "units_without_citation": citations["units_without_citation"],
            "cross_leaf_repetition_pairs": repetition,
        },
        "reached_1000_words": word_count >= 1000,
    }

    all_clean = (
        metrics["fidelity_pass_rate"] == 1.0
        and coverage["coverage"] == 1.0
        and not citations["broken"]
        and not citations["units_without_citation"]
        and not repetition
    )

    prose = (
        f"{n} single-fact leaves, each rewritten independently via {MODEL_NAME}'s decoding-constrained path "
        f"(EXP-064's measured 1.0-fidelity configuration): fidelity pass rate {metrics['fidelity_pass_rate']} "
        f"(fail reasons: {fail_reason_counts}). Joined document: {word_count} words in {metrics['total_elapsed_sec']}s "
        f"({metrics['sec_per_leaf']}s/leaf). Document-level: coverage {coverage['coverage']}, "
        f"{len(citations['broken'])} broken citation(s), {len(citations['units_without_citation'])} unit(s) missing a "
        f"citation entirely, {len(repetition)} cross-leaf repetition pair(s) (a check no single-leaf fidelity "
        f"gate can see -- two different leaves independently drifting toward near-identical phrasing)."
    )

    conclusion = (
        (
            f"Chaining the bounded rewriter's own small, bounded generation step across {n} leaves to reach "
            f"{word_count} words holds up completely: per-leaf fidelity stayed at the same 1.0 EXP-064 measured "
            "on 13 leaves, and none of the three document-level failure modes EXP-018 checked for the "
            "deterministic path at far larger scale (coverage gaps, broken citations, repetition) appeared "
            "here either, including the cross-leaf repetition check no per-leaf gate could have caught on its "
            "own. The project owner's concern was real and worth checking directly -- EXP-018 only ever proved "
            "scale for the path that generates nothing, and this is the first measurement of the generative "
            "path at anything beyond a 13-finding fixture -- but at this scale and leaf size, it does not "
            "degrade."
            if all_clean
            else f"Chaining across {n} leaves did NOT hold up as cleanly as the 13-leaf measurement: "
            f"{metrics['fidelity_pass_rate']} fidelity pass rate, and the document-level checks found "
            f"{len(citations['broken'])} broken citation(s), {len(citations['units_without_citation'])} missing "
            f"citation(s), {len(repetition)} cross-leaf repetition pair(s). This is the honest result, not "
            "smoothed into a clean pass -- the specific failures matter more than the aggregate rate, and are "
            "in items.json and document_level above, not averaged away."
        )
    )

    run.finish(
        title="Does per-leaf generative fidelity hold up at real document scale?",
        goal=(
            "Measure whether the bounded rewriter's proven small-scale fidelity (EXP-064: 1.0 on 13 leaves) "
            "holds when chained across enough leaves to reach genuine document length, and check document-"
            "level properties (coverage, citation integrity, cross-leaf repetition) no single-leaf fidelity "
            "gate can see on its own -- the output-side scale question EXP-018 never actually tested, since "
            "it only stress-tested the deterministic, nothing-generated path."
        ),
        method=(
            f"{N_LEAVES} single-fact synthetic leaves (lab.common.synthetic_fusion_data, seed={SEED}, a fresh "
            "seed not overlapping EXP-073's train/eval splits), each rewritten independently via "
            "lab.common.real_rewriter_ollama.rewrite_unit_constrained (gemma3:270m, decoding-constrained -- "
            "the identical configuration EXP-064 measured at 1.0 fidelity on 13 leaves). Joined into one "
            "document, then checked with the identical functions (lab.common.assemble.coverage_report/"
            "citation_integrity/repetition_pairs) EXP-018 used to validate the deterministic path at scale."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "80 leaves / ~1,000+ words, not EXP-018's 5,000-claim/42,506-word extreme -- real generation calls "
            "are far slower than deterministic joining, so this targets genuinely document-length output "
            "(matching the project owner's own 'rewrite 1000' framing) rather than matching EXP-018's upper "
            "bound call for call."
        ),
        referenced_files=FILES,
        follow_ups=[
            "Not yet tested at EXP-018's full scale (1,000-5,000 leaves) -- this answers 'does it hold at "
            "document length', not 'does it hold at EXP-018's upper bound', which would take substantially "
            "longer with real generation calls.",
            "Only single-fact leaves tested here, deliberately, to isolate the scale question from the "
            "already-confirmed multi-fact-leaf problem (EXP-064/073). A mixed-leaf-size scale test is a "
            "separate, harder follow-up.",
            "Not yet wired into lab.common.brain.reason as the 'does the ask want a document' fifth signal "
            "brain.py's own docstring already names as a todo -- this measures the mechanism standalone, not "
            "through the unified entry point.",
        ],
        models_used=f"{MODEL_NAME} via Ollama, decoding-constrained, rewriter role only -- the same checkpoint and configuration EXP-064 measured, now at scale instead of on 13 leaves.",
    )


if __name__ == "__main__":
    main()
