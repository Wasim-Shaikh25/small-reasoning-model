"""EXP-094: exception/condition handling for the threshold-rule branch.

Named as a gap by EXP-089/091/026's own scale_down since EXP-089 first
wired exception-checking into brain.reason: "Only the verb-trigger rule
shape is wired -- the threshold-rule branch (apply_threshold_rule) does
not go through split_exceptions/check_exceptions at all... a real and
separate gap if a threshold rule's own consequence ever carries an
'unless' clause." Verified: EXP-057/058/059's own threshold fixtures
never exercised this, because none of their policy sentences carry a
trailing exception clause.

The fix (lab/common/brain.py, this exploration): the threshold-rule
branch's `if applied["matched"]:` case now calls split_exceptions/
check_exceptions exactly the way the verb-rule branch already does
(same polarity-aware EXP-026 mechanism), checking every OTHER given
passage as context. Purely additive -- when a threshold rule's
consequence has no exception/condition clause at all (every existing
fixture: EXP-057/058/059/060/066/068/070), check_exceptions returns
"no_exception" and the output text is byte-identical to before this
change. Verified directly: reran EXP-060/066/068/070 (the explorations
that actually exercise this branch through brain.reason -- EXP-058/059
predate brain.reason's unification and never touch this code path at
all) and confirmed identical results.

Three new cases prove the actual new capability, none of which existed
in any prior fixture:
  1. A threshold rule with a trailing "unless" clause, context affirms
     the exception -> blocked.
  2. The same rule, context contradicts the exception -> applies
     cleanly.
  3. The same rule, no context -> applies but flagged unresolved.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/tests/exp_094_threshold_exception/run.py",
    "lab/common/brain.py",
    "lab/common/inference.py",
    "lab/common/rules.py",
    "lab/tests/exp_060_unified_brain/run.py",
]

ASK = "How much money has the contractor billed in total this quarter, and does company policy require finance head approval?"
RULE_TEXT = "Company policy: if a contractor's total billed amount in a quarter exceeds INR 30000, the payment requires finance head approval, unless the finance head has pre-approved the vendor in writing."
RULE_PASSAGE = {"id": "policy", "text": RULE_TEXT}
CONTRACTOR_PASSAGE = {"id": "fact-1", "text": "Priya Nair (a contractor) billed INR 40000 this quarter."}
APPROVED_PASSAGE = {"id": "context-approved", "text": "The finance head has pre-approved the vendor in writing."}
NOT_APPROVED_PASSAGE = {"id": "context-not-approved", "text": "The finance head has never reviewed or approved this vendor."}


def main():
    run = Run("EXP-094", "exp_094_threshold_exception")

    case1 = reason(ASK, [RULE_PASSAGE, CONTRACTOR_PASSAGE, APPROVED_PASSAGE])
    case1_blocked = "policy does not apply" in case1["text"] and "policy applies" not in case1["text"]

    case2 = reason(ASK, [RULE_PASSAGE, CONTRACTOR_PASSAGE, NOT_APPROVED_PASSAGE])
    case2_clean = case2["decision"] == "supported" and "policy applies" in case2["text"] and "unresolved" not in case2["text"]

    case3 = reason(ASK, [RULE_PASSAGE, CONTRACTOR_PASSAGE])
    case3_flagged = case3["decision"] == "supported_with_flags" and "unresolved" in case3["text"]

    run.write_json(
        "cases.json",
        {"case1_exception_holds": case1, "case2_exception_contradicted": case2, "case3_no_context": case3},
    )

    all_correct = case1_blocked and case2_clean and case3_flagged

    metrics = {
        "case1_exception_holds": {"decision": case1["decision"], "text": case1["text"], "blocked": case1_blocked},
        "case2_exception_contradicted": {"decision": case2["decision"], "text": case2["text"], "clean": case2_clean},
        "case3_no_context": {"decision": case3["decision"], "text": case3["text"], "flagged": case3_flagged},
        "all_correct": all_correct,
    }

    prose = (
        f"Case 1 (exception affirmed): decision='{case1['decision']}', text={case1['text']!r} -- "
        f"blocked={case1_blocked}. Case 2 (exception contradicted): decision='{case2['decision']}', text="
        f"{case2['text']!r} -- clean={case2_clean}. Case 3 (no context): decision='{case3['decision']}', "
        f"text={case3['text']!r} -- flagged={case3_flagged}. None of these three cases was reachable before "
        f"this fix -- every prior threshold-rule fixture (EXP-057/058/059/060/066/068/070) had no exception "
        f"clause at all, so the gap was never exercised, only named."
    )

    conclusion = (
        "The threshold-rule branch now checks exceptions/conditions exactly like the verb-rule branch "
        "already did, closing the gap EXP-089 named as a separate, un-fixed limit. Purely additive: every "
        "existing threshold-rule fixture (reran EXP-060/066/068/070, the explorations that actually exercise "
        "this branch through brain.reason) produced byte-identical output, since check_exceptions correctly "
        "returns 'no_exception' when there is nothing to check."
        if all_correct
        else "At least one case did not behave as expected -- see metrics, reported as measured."
    )

    run.finish(
        title="Exception/condition handling for the threshold-rule branch, closing a gap named since EXP-089",
        goal=(
            "Give lab.common.brain's threshold-rule branch the same split_exceptions/check_exceptions call "
            "the verb-rule branch has had since EXP-089 -- a gap that exploration's own scale_down named "
            "explicitly ('a real and separate gap if a threshold rule's own consequence ever carries an "
            "unless clause') but left unfixed."
        ),
        method=(
            "lab.common.brain.py's threshold-rule `if applied['matched']:` branch now calls split_exceptions/"
            "check_exceptions (both unchanged, the same polarity-aware EXP-026 mechanism) against every other "
            "given passage as context, mirroring the verb-rule branch exactly. Three new cases (exception "
            "affirmed/contradicted/unresolved) prove the new capability, none reachable by any prior fixture. "
            "Reran EXP-060/066/068/070 (the explorations that actually exercise this branch through "
            "brain.reason -- EXP-058/059 predate reason()'s unification and never touch this code at all) to "
            "confirm zero behavior change."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "Only verified against one hand-built threshold-rule-with-exception fixture, not a sweep across "
            "many threshold-rule phrasings. _role_matches's own role-mismatch check still runs first and is "
            "unaffected by this change -- a role mismatch still short-circuits before any exception check, "
            "same as before."
        ),
        referenced_files=FILES,
        follow_ups=[],
        models_used=(
            "Same as EXP-089/026: spaCy dependency parser (unchanged) + MoritzLaurer/DeBERTa-v3-base-mnli-"
            "fever-anli via the existing, unmodified check_exception/check_exceptions. No generative model."
        ),
    )

    print("case1_blocked:", case1_blocked, "case2_clean:", case2_clean, "case3_flagged:", case3_flagged)


if __name__ == "__main__":
    main()
