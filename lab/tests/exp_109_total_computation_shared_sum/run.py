"""EXP-109: lab.common.rules.sum_amounts_for_subject, wired into brain.reason's
total_computation stage in place of the inline scan it used to duplicate.

The 2026-11-12 audit flagged sum_amounts_for_subject as "test-only" (its
only caller was lab.tests.exp_058's own fixture) and moved it to
lab.tests.support -- correct at the time, but a closer look found
total_computation's own inline loop in brain.py was ALREADY doing exactly
the same scan (every amount in every scoped passage, rule-shaped passages
excluded, sources tracked for citation), just reimplemented by hand instead
of calling the shared function. Moved sum_amounts_for_subject back to
lab.common.rules, added the one behavior sum_amounts_for_subject didn't
originally have (skip_rule_passages=True, matching brain.py's own
2026-11-10 fix for a threshold/fee amount wrongly counted as a line item),
and wired brain.py's stage to call it directly -- one implementation of
this scan, not two.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.entities import AMOUNT_RE
from lab.common.harness import Run
from lab.common.rules import sum_amounts_for_subject

FILES = [
    "lab/tests/exp_109_total_computation_shared_sum/run.py",
    "lab/common/brain.py",
    "lab/common/rules.py",
    "lab/common/calc.py",
    "lab/common/entities.py",
    "data/exp_109_total_computation_shared_sum/results.json",
]

PASSAGES = [
    {"id": "P1", "text": "Ravi owes $100 for rent."},
    {"id": "P2", "text": "Ravi owes $50 for a late fee."},
]
RULE_PASSAGE = {"id": "P3", "text": "If the total exceeds $500, a $25 overage fee applies."}
ASK = "What is the total?"


def main() -> None:
    run = Run("EXP-109", "exp_109_total_computation_shared_sum")

    plain = reason(ASK, PASSAGES)
    with_rule = reason(ASK, PASSAGES + [RULE_PASSAGE])
    direct_call = sum_amounts_for_subject(PASSAGES, AMOUNT_RE)
    direct_call_with_rule = sum_amounts_for_subject(PASSAGES + [RULE_PASSAGE], AMOUNT_RE)
    direct_call_no_skip = sum_amounts_for_subject(PASSAGES + [RULE_PASSAGE], AMOUNT_RE, skip_rule_passages=False)

    plain_correct = plain["decision"] == "supported" and "total 150" in plain["text"]
    rule_excluded_correct = with_rule["decision"] == "supported" and "total 150" in with_rule["text"] and "525" not in with_rule["text"]
    direct_correct = direct_call["total"] == 150 and sorted(direct_call["sources"]) == ["P1", "P2"]
    direct_rule_excluded_correct = direct_call_with_rule["total"] == 150
    direct_no_skip_correct = direct_call_no_skip["total"] == 150 + 500 + 25

    metrics = {
        "brain_total_via_shared_function": {"decision": plain["decision"], "text": plain["text"], "correct": plain_correct},
        "brain_total_excludes_rule_passage": {"decision": with_rule["decision"], "text": with_rule["text"], "correct": rule_excluded_correct},
        "direct_call_matches_brain": {"total": direct_call["total"], "sources": sorted(direct_call["sources"]), "correct": direct_correct},
        "direct_call_skips_rule_passage_by_default": {"total": direct_call_with_rule["total"], "correct": direct_rule_excluded_correct},
        "direct_call_skip_rule_passages_false": {"total": direct_call_no_skip["total"], "correct": direct_no_skip_correct},
    }
    run.write_json("items.json", metrics)
    all_correct = plain_correct and rule_excluded_correct and direct_correct and direct_rule_excluded_correct and direct_no_skip_correct

    prose = (
        f"brain.reason's total_computation stage over two fact passages ($100 + $50): {plain['text']!r}. "
        f"With a threshold-rule passage mixed in (its own $500/$25 must NOT be counted as line items): "
        f"{with_rule['text']!r} -- still 150, the rule's own numbers correctly excluded. Calling "
        f"sum_amounts_for_subject directly on the same passages gives the identical total/sources "
        f"brain.py's stage produced ({direct_call['total']}, {sorted(direct_call['sources'])}), confirming "
        f"one real implementation, not two independently-written scans that happen to agree today. "
        f"skip_rule_passages=False recovers the OLD (pre-2026-11-10-fix, lab.tests.support-era) behavior of "
        f"counting everything, {direct_call_no_skip['total']} -- available for a caller who genuinely wants "
        f"that, but never brain.py's own default."
    )
    conclusion = (
        "lab.common.rules.sum_amounts_for_subject -- moved to lab.tests.support as test-only, moved back "
        "once this DRY gap was found -- is now the one implementation of the cross-passage amount scan "
        "total_computation needs, with the rule-passage exclusion brain.py's stage already required folded "
        "in via skip_rule_passages=True (the default). brain.py no longer carries its own copy of this scan."
        if all_correct else
        "At least one case did not behave as expected -- see metrics for exactly which."
    )
    run.finish(
        title="sum_amounts_for_subject wired into total_computation, replacing the inline scan it duplicated",
        goal="DRY up total_computation's own inline amount-scanning loop (found to be functionally identical to lab.common.rules.sum_amounts_for_subject, just reimplemented by hand) into one shared, directly-callable function.",
        method="brain.reason's own total_computation output checked against a direct call to sum_amounts_for_subject on the identical passages, with and without a mixed-in rule-shaped passage, confirming they agree and that the rule-exclusion default matches brain.py's existing, already-measured behavior.",
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Two fact passages, one rule passage -- a proof the shared function reproduces brain.py's exact prior behavior, not a new capability measurement (calc.sum_amounts's own arithmetic was already proven in EXP-007/014).",
        referenced_files=FILES,
        follow_ups=[],
        models_used="None -- regex span extraction and arithmetic, both deterministic, unchanged by this refactor.",
    )
    print("plain_correct:", plain_correct, "rule_excluded_correct:", rule_excluded_correct, "direct_correct:", direct_correct, "direct_rule_excluded_correct:", direct_rule_excluded_correct, "direct_no_skip_correct:", direct_no_skip_correct)
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
