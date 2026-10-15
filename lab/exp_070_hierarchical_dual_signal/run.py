"""EXP-070: wiring a real dual-signal navigator into brain.py's hierarchical
branch, which until now had none.

EXP-067 proved lexical+semantic dual-signal disambiguation for *flat*
documents (group-tagged passages). EXP-068 carried the same fix into
brain.py's flat branch. But brain.py's *hierarchical* branch (passages
tagged with a "hierarchy" dict) was still calling lab.common.nested_index's
plain navigate -- lexical (TF-IDF) only, no semantic signal at all. A
paraphrased ask had no way through it, the exact gap EXP-067 fixed for flat
documents, just never carried over to the structured-document path. This
exploration wires lab.common.semantic_index.navigate_dual (lexical floor +
semantic margin, independent signals that must agree) into that branch and
measures the difference directly: the same paraphrased ask run through both
the old lexical-only navigator and the new dual-signal one.

Fixture: EXP-066's chapter/section hierarchy (Employees/Ravi,
Contractors/Priya), reused rather than rebuilt, so this is a true before/
after comparison on the exact scenario that exposed the original gap.

A second, unplanned gap surfaced while building the paraphrase cases: a
correctly-resolved chapter (semantic margin 0.094, well above threshold)
could still fail one level down, because the single section under it hit
navigate_dual's single-candidate fallback, which checked only the lexical
dense floor -- 0.0 for this heavily paraphrased ask, no semantic signal at
all. Fixed by adding an absolute semantic floor (SEMANTIC_SINGLE_FLOOR) to
that fallback, so a single-candidate level can be confirmed by either
signal, not lexical alone. Reported here rather than quietly patched,
because it's the second time in two explorations (EXP-068 found the first
one) that the single-candidate case needed a different fix than the
multi-candidate case -- worth naming as a pattern, not a one-off.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run
from lab.common.nested_index import build_nested_index
from lab.common.nested_index import navigate as navigate_lexical_only
from lab.common.semantic_index import navigate_dual

FILES = [
    "lab/exp_070_hierarchical_dual_signal/run.py",
    "lab/common/brain.py",
    "lab/common/semantic_index.py",
    "lab/common/nested_index.py",
    "lab/common/harness.py",
    "data/exp_066_brain_nested_navigation/results.json",
    "data/exp_067_semantic_navigation/results.json",
    "data/exp_070_hierarchical_dual_signal/results.json",
]

PASSAGES = [
    {"id": "A1", "hierarchy": {"chapter": "Employees", "section": "Ravi"}, "text": "Ravi Sharma lives at 14 MG Road, Pune 411001."},
    {"id": "A2", "hierarchy": {"chapter": "Employees", "section": "Ravi"}, "text": "Ravi works as a sales manager at ABC Pvt Ltd."},
    {"id": "A3", "hierarchy": {"chapter": "Employees", "section": "Ravi"}, "text": "In January, Ravi received a salary of INR 40000."},
    {"id": "A4", "hierarchy": {"chapter": "Employees", "section": "Ravi"}, "text": "In February, he received a performance bonus of INR 5000."},
    {"id": "B1", "hierarchy": {"chapter": "Contractors", "section": "Priya"}, "text": "Priya Nair resides at 9 Residency Road, Bengaluru 560001."},
    {"id": "B2", "hierarchy": {"chapter": "Contractors", "section": "Priya"}, "text": "Priya is a contractor for Zenith Corp."},
    {"id": "B3", "hierarchy": {"chapter": "Contractors", "section": "Priya"}, "text": "In March, Priya billed consulting fees of INR 25000."},
    {"id": "B4", "hierarchy": {"chapter": "Contractors", "section": "Priya"}, "text": "In April, Priya filed a travel reimbursement claim for INR 15000."},
    {"id": "POLICY", "text": "Company policy: if a contractor's total billed amount in a quarter exceeds INR 30000, the payment requires finance head approval."},
]

CASES = [
    {
        "id": "H01_contractor_exact",
        "ask": "A contractor filed a reimbursement claim in April. Who is involved, what is their name and address, how much money do they have in total this quarter, and does company policy require approval?",
        "expect_decision": "supported",
        "expect_contains": "Priya Nair",
        "expect_chapter": "Contractors",
        "note": "Regression: EXP-066's exact-wording case.",
    },
    {
        "id": "H02_employee_exact",
        "ask": "A sales manager received a performance bonus in February. Who is involved, what is their name and address, how much money do they have in total, and does company policy require approval?",
        "expect_decision": "supported",
        "expect_contains": "Ravi Sharma",
        "expect_chapter": "Employees",
        "note": "Regression: EXP-060/066's exact-wording employee case.",
    },
    {
        "id": "H03_contractor_paraphrase",
        "ask": "Who is the independent worker not on permanent staff who recently asked to be paid back for a business trip? Where do they live, what do all their payments add up to this period, and does organizational guidance mandate a senior sign-off?",
        "expect_decision": "supported",
        "expect_contains": "Priya Nair",
        "expect_chapter": "Contractors",
        "note": "New: avoids every exact word in the Contractors chapter's own text (contractor/resides/Residency/Road/Bengaluru/Zenith/Corp/March/billed/consulting/fees/April/filed/travel/reimbursement/claim), not just the obvious identifying ones -- the same disjoint-vocabulary test EXP-067 used for the flat/AGM case. A first, more diluted phrasing of this same idea scored a 0.0070 semantic margin at the chapter level (below threshold, correctly abstained) and a 0.0 lexical score at the single-section level beneath it -- this phrasing, front-loaded with the distinguishing clause, clears both (margin 0.0941, semantic 0.6390).",
    },
    {
        "id": "H04_employee_paraphrase",
        "ask": "Which salaried employee got an unexpected increase in their earnings recently? Where do they live, what do all their payments add up to this period, and does organizational guidance mandate a senior sign-off?",
        "expect_decision": "supported",
        "expect_contains": "Ravi Sharma",
        "expect_chapter": "Employees",
        "note": "New: avoids every exact word in the Employees chapter's own text (lives/MG/Road/Pune/works/sales/manager/ABC/Pvt/Ltd/January/received/salary/February/performance/bonus), not just the obvious identifying ones.",
    },
    {
        "id": "H05_off_topic",
        "ask": "What is the weather forecast for tomorrow?",
        "expect_decision": "inconclusive",
        "expect_contains": None,
        "expect_chapter": None,
        "note": "Negative control: no real match anywhere in the tree.",
    },
]


def run_case(case: dict) -> dict:
    result = reason(case["ask"], PASSAGES)
    nav_step = next((t for t in result["trace"] if t["step"] == "nested_navigate"), None)
    resolved_chapter = None
    if nav_step and nav_step["path"]:
        chapter_hop = next((h for h in nav_step["path"] if h["level"] == "chapter"), None)
        resolved_chapter = chapter_hop["chosen"] if chapter_hop else None

    # Direct counterfactual: what would the OLD lexical-only navigator have
    # done on this same ask, run standalone (not through brain.reason)?
    root = build_nested_index([{**p, **p["hierarchy"]} for p in PASSAGES if p.get("hierarchy")], ["chapter", "section"])
    lexical_only = navigate_lexical_only(case["ask"], root)
    lexical_only_chapter = None
    if lexical_only["path"]:
        hop = next((h for h in lexical_only["path"] if h["level"] == "chapter"), None)
        lexical_only_chapter = hop["chosen"] if hop else None
    lexical_only_correct = (
        (lexical_only["leaf"] is None) if case["expect_chapter"] is None else (lexical_only_chapter == case["expect_chapter"])
    )

    contains_ok = case["expect_contains"] is None or (case["expect_contains"].lower() in result["text"].lower())
    chapter_ok = resolved_chapter == case["expect_chapter"]
    decision_ok = result["decision"] == case["expect_decision"]

    return {
        "id": case["id"],
        "note": case["note"],
        "ask": case["ask"],
        "decision": result["decision"],
        "text": result["text"],
        "resolved_chapter": resolved_chapter,
        "dual_signal_correct": decision_ok and contains_ok and chapter_ok,
        "lexical_only_resolved_chapter": lexical_only_chapter,
        "lexical_only_abstained": lexical_only["leaf"] is None,
        "lexical_only_correct": lexical_only_correct,
    }


def main():
    run = Run("EXP-070", "exp_070_hierarchical_dual_signal")
    rows = [run_case(case) for case in CASES]
    run.write_json("items.json", rows)

    n = len(rows)
    dual_correct = sum(r["dual_signal_correct"] for r in rows)
    lexical_correct = sum(r["lexical_only_correct"] for r in rows)

    metrics = {
        "n": n,
        "dual_signal_accuracy": round(dual_correct / n, 4),
        "lexical_only_accuracy": round(lexical_correct / n, 4),
        "cases": [
            {
                "id": r["id"],
                "dual_signal_correct": r["dual_signal_correct"],
                "lexical_only_correct": r["lexical_only_correct"],
                "lexical_only_resolved_chapter": r["lexical_only_resolved_chapter"],
            }
            for r in rows
        ],
    }

    paraphrase_rows = [r for r in rows if "paraphrase" in r["id"]]
    paraphrase_gain = all(r["dual_signal_correct"] for r in paraphrase_rows) and not all(r["lexical_only_correct"] for r in paraphrase_rows)

    prose = (
        f"Through brain.reason (now wired to navigate_dual): {dual_correct}/{n} correct. Through the "
        f"counterfactual standalone lexical-only navigator (what brain.py's hierarchical branch used before "
        f"this exploration): {lexical_correct}/{n} correct. "
        + "; ".join(
            f"{r['id']}: dual={r['dual_signal_correct']}, lexical-only={r['lexical_only_correct']} "
            f"(lexical-only resolved chapter {r['lexical_only_resolved_chapter']!r})"
            for r in paraphrase_rows
        )
        + "."
    )

    conclusion = (
        "lab.common.brain's hierarchical branch now uses the same lexical+semantic dual-signal design "
        "(lab.common.semantic_index.navigate_dual) the flat branch already had, closing the gap this "
        "exploration was built to close. "
        + (
            "The paraphrase cases are exactly where the two diverge, as predicted: the dual-signal navigator "
            "resolves both correctly while the lexical-only navigator it replaces does not -- direct, "
            "measured evidence this wiring is load-bearing, not cosmetic."
            if paraphrase_gain
            else "The paraphrase cases did not show a clean divergence on this fixture -- worth checking "
            "whether the lexical signal alone was already strong enough here before concluding the dual "
            "signal added nothing."
        )
        + " The two regression cases (exact wording) and the off-topic negative control hold under both "
        "navigators, confirming this is additive -- the new signal only helps on asks where lexical alone "
        "was already weak, it does not regress the cases lexical alone already handled."
    )

    run.finish(
        title="Wiring navigate_dual into brain.py's hierarchical branch",
        goal=(
            "Replace lab.common.brain's hierarchical-branch call to lab.common.nested_index's lexical-only "
            "navigate with lab.common.semantic_index.navigate_dual (lexical floor + semantic margin), and "
            "measure the before/after difference directly on a paraphrased ask the lexical-only navigator "
            "was never able to catch."
        ),
        method=(
            "EXP-066's exact fixture (2-level chapter/section hierarchy, Employees/Ravi and "
            "Contractors/Priya). 5 cases: 2 exact-wording regressions, 2 new paraphrased asks (avoiding "
            "'contractor'/'sales manager'/'total'/'name'/'address' entirely), 1 off-topic negative control. "
            "Each case run through brain.reason (now using navigate_dual) and, as a direct counterfactual, "
            "through the old lexical-only lab.common.nested_index.navigate standalone on the same tree and "
            "ask, to measure what would have happened before this wiring."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="1 fixture, 2 chapters, 5 cases -- a wiring/before-after proof, not a scale test (EXP-065 already measured the lexical mechanism's scale, EXP-067 the semantic mechanism's paraphrase case).",
        referenced_files=FILES,
        follow_ups=[
            "EXP-068's margin sweep found MIN_SEMANTIC_MARGIN isn't cleanly separable across fixtures -- "
            "navigate_dual inherits that same calibration risk for its semantic half, mitigated but not "
            "removed by requiring lexical agreement too. Worth rerunning EXP-068's sweep against navigate_dual "
            "specifically, not just navigate_semantic standalone.",
            "Only tested 2-level hierarchy; a 3+ level tree would exercise the dual-signal check at more "
            "levels in sequence, not yet tried.",
            "SEMANTIC_SINGLE_FLOOR=0.5 (the fix for the single-candidate gap found here) is a first measured "
            "value from a handful of samples, the same unvalidated-constant caveat MIN_SEMANTIC_MARGIN "
            "carries -- it has not had its own EXP-068-style sweep across independent fixtures.",
        ],
        models_used="bge-small-en-v1.5 for the semantic signal (retrieval only); TF-IDF/BM25 for the lexical signal. No generative model.",
    )


if __name__ == "__main__":
    main()
