"""EXP-053: cross-page consistency check for book-length assembly.

EXP-078 already proved the mechanism (lab.common.working_memory.
WorkingMemory) end to end through the full write_long_document pipeline,
at 6-7 leaves, and its own conclusion says so directly: "This closes
EXP-053's gap directly." That claim was correct in substance but this
stub's own entry in EXPLORATIONS.md was never actually updated to
`closed` -- a bookkeeping gap, not a missing capability. This exploration
closes it formally under its own id, and goes further than EXP-078 did in
one respect: EXP-053's own named goal was specifically "page 40 against
page 4" (book-length, not a 6-7 leaf proof), so this calls WorkingMemory
directly (not through the full generative-rewriter pipeline, which
EXP-077/078 already measured separately) across 40 simulated pages, to
check the mechanism scales to the distance its own goal named -- an early
page's claim is still checked against 36 pages later, not just its
immediate neighbor.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.working_memory import WorkingMemory

FILES = [
    "lab/tests/exp_053_cross_page_consistency/run.py",
    "lab/common/working_memory.py",
    "lab/common/rules.py",
    "data/exp_078_longform_consistency/results.json",
]


def main():
    run = Run("EXP-053", "exp_053_cross_page_consistency")

    memory = WorkingMemory()
    all_flags = []

    # Page 4: the earliest claim about Ravi Sharma's address.
    for i in range(40):
        if i == 3:
            text = "Ravi Sharma lives at 14 MG Road, Pune 411001."
        elif i == 39:
            # Page 40: the same subject+verb, a different value -- 36
            # pages later, the exact distance EXP-053's own goal named
            # ("page 40 against page 4"), not an adjacent-page check.
            text = "Ravi Sharma lives at 88 New Colony Road, Nagpur 440001."
        else:
            text = f"Person {i} works at Company {i} Pvt Ltd."
        flags = memory.check_and_remember_page(f"page-{i + 1}", text, [f"C{i}"])
        all_flags.extend(flags)

    conflict = next((f for f in all_flags if f["subject"] == "Ravi Sharma"), None)
    distance_correct = conflict is not None and conflict["leaf_id"] == "page-40" and conflict["conflicts_with_leaf_id"] == "page-4"
    no_other_flags = len(all_flags) == 1
    pages_remembered = len(memory.pages) == 40

    run.write_json("flags.json", {"all_flags": all_flags, "pages_remembered": pages_remembered})

    all_correct = distance_correct and no_other_flags and pages_remembered

    metrics = {
        "n_pages": 40,
        "n_flags": len(all_flags),
        "conflict_flag": conflict,
        "distance_correct": distance_correct,
        "no_other_flags": no_other_flags,
        "pages_remembered": pages_remembered,
        "all_correct": all_correct,
    }

    prose = (
        f"40 simulated pages, one claim about Ravi Sharma's address on page 4 and a contradicting claim about "
        f"the same subject+verb on page 40 (36 pages later): {len(all_flags)} flag(s) fired, "
        f"{conflict!r}. The flag correctly names page-40 as the source and page-4 as what it conflicts with "
        f"({distance_correct}), with no other page (37 unrelated pages in between, each about a different "
        f"person) producing a false-positive flag ({no_other_flags})."
    )

    conclusion = (
        "EXP-053's own named goal -- 'page 40 against page 4', not just an adjacent-page check -- is met: "
        "WorkingMemory's bounded per-page digest (subject-verb-object triples only, never full page text) "
        "still catches a contradiction 36 pages apart with zero false positives among 37 unrelated pages in "
        "between. The mechanism itself was already proven through the full pipeline by EXP-078 ('this closes "
        "EXP-053's gap directly', its own conclusion) -- this exploration closes EXP-053's own stub entry "
        "formally and checks the specific book-length distance its goal named, which EXP-078's 6-7 leaf fixture "
        "did not."
        if all_correct
        else "At least one check did not come out as expected -- see metrics, reported as measured."
    )

    run.finish(
        title="Cross-page consistency check for book-length assembly, closed formally and checked at real distance",
        goal=(
            "Close EXP-053's own stub entry (EXPLORATIONS.md still listed it as `todo` despite EXP-078's "
            "conclusion already stating 'this closes EXP-053's gap directly' -- a bookkeeping gap) and check "
            "the specific distance EXP-053's own goal named ('page 40 against page 4'), which EXP-078's 6-7 "
            "leaf fixture never actually exercised."
        ),
        method=(
            "lab.common.working_memory.WorkingMemory (already built, unchanged) called directly across 40 "
            "simulated pages: page 4 states a fact about Ravi Sharma, 35 unrelated pages follow, page 40 "
            "restates the same subject+verb with a different value. Checks the flag fires, names the correct "
            "two pages, and that none of the 37 unrelated pages produces a false positive."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "Calls WorkingMemory directly, not through the full write_long_document pipeline with a generative "
            "rewriter on top -- EXP-077/078 already measured that combination separately at smaller scale; "
            "this exploration isolates the consistency-check mechanism itself at the distance its own goal "
            "named. 40 pages, one injected conflict, not an exhaustive search over conflict positions."
        ),
        referenced_files=FILES,
        follow_ups=[],
        models_used=(
            "lab.common.rules.extract_fact_triple (spaCy dependency parse, deterministic, unchanged). No "
            "generative model, no new dependency."
        ),
    )

    print("distance_correct:", distance_correct, "no_other_flags:", no_other_flags, "pages_remembered:", pages_remembered)


if __name__ == "__main__":
    main()
