"""EXP-097: temporal bound reasoning (until/before/after/once), the
genuinely new reasoning primitive TEMPORAL_BOUND connectives needed --
not just another entry in a lookup table, since "is this proposition
true" (the only question check_exception/check_exceptions can answer)
is the wrong question for "has a point in time been reached yet".

lab.common.temporal (new) adds that second primitive: find_temporal_bound
splits a rule's consequence into (main_clause, bound_clause, direction)
the same single-point way split_exceptions already does for CONDITION_
NEGATIVE/POSITIVE; check_temporal_bound resolves it two ways --
deterministically if the bound clause is a literal date (lab.common.
calc.parse_date, already used for EXP-007/014's arithmetic), or via one
bounded NLI judgment (reusing check_exception, never duplicating it) if
the bound clause names an event instead. lab.common.brain's new
_check_rule_gate unifies this with the existing condition/exception
gate behind one interface, so both of reason()'s rule-application
branches (verb-trigger and threshold) get temporal reasoning for free,
without needing to know which kind of gate they got.

Five cases through lab.common.brain.reason(ask, passages) itself:
  1. Absolute date clearly in the past ("until 1 January 2020") ->
     bound reached -> blocked ("not currently satisfied").
  2. Absolute date clearly in the future ("until 1 January 2030") ->
     bound not reached -> applies cleanly.
  3. Event-relative "until", context affirms the event occurred ->
     blocked.
  4. Event-relative "until", context contradicts it -> applies cleanly.
  5. Event-relative "after" (opposite direction from "until"), context
     affirms the event occurred -> applies cleanly (the OPPOSITE of
     what the same context would do for an "until" rule -- direction
     is not interchangeable, EXP-090's own finding, now proven to
     matter for actual reasoning outcomes, not just detection labels).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/tests/exp_097_temporal_reasoning/run.py",
    "lab/common/temporal.py",
    "lab/common/brain.py",
    "lab/common/inference.py",
    "lab/common/calc.py",
    "lab/common/connectives.py",
]

ASK = "Does MedCorp's processing of Aisha's data comply with the rule?"
FACT_PASSAGE = {"id": "fact-1", "text": "MedCorp processed Aisha."}
WITHDRAWN_CONTEXT = {"id": "context-withdrawn", "text": "Aisha withdrew her consent last month."}
NOT_WITHDRAWN_CONTEXT = {"id": "context-active", "text": "Aisha has never withdrawn her consent."}

RULE_PAST_DATE = {"id": "rule-past", "text": "If anyone processes special category data, it is lawful until 1 January 2020."}
RULE_FUTURE_DATE = {"id": "rule-future", "text": "If anyone processes special category data, it is lawful until 1 January 2030."}
RULE_UNTIL_EVENT = {"id": "rule-until-event", "text": "If anyone processes special category data, it is lawful until the data subject withdraws consent."}
RULE_AFTER_EVENT = {"id": "rule-after-event", "text": "If anyone processes special category data, it is lawful after the data subject withdraws consent."}


def main():
    run = Run("EXP-097", "exp_097_temporal_reasoning")

    case1 = reason(ASK, [RULE_PAST_DATE, FACT_PASSAGE])
    case1_blocked = "policy does not apply" in case1["text"] and "temporal bound" in case1["text"]

    case2 = reason(ASK, [RULE_FUTURE_DATE, FACT_PASSAGE])
    case2_clean = case2["decision"] == "supported" and "Therefore" in case2["text"]

    case3 = reason(ASK, [RULE_UNTIL_EVENT, FACT_PASSAGE, WITHDRAWN_CONTEXT])
    case3_blocked = "policy does not apply" in case3["text"] and "temporal bound" in case3["text"]

    case4 = reason(ASK, [RULE_UNTIL_EVENT, FACT_PASSAGE, NOT_WITHDRAWN_CONTEXT])
    case4_clean = case4["decision"] == "supported" and "Therefore" in case4["text"]

    case5 = reason(ASK, [RULE_AFTER_EVENT, FACT_PASSAGE, WITHDRAWN_CONTEXT])
    case5_clean = case5["decision"] == "supported" and "Therefore" in case5["text"]

    run.write_json(
        "cases.json",
        {
            "case1_past_date_blocked": case1,
            "case2_future_date_clean": case2,
            "case3_event_withdrawn_blocked": case3,
            "case4_event_active_clean": case4,
            "case5_after_direction_reversed": case5,
        },
    )

    all_correct = case1_blocked and case2_clean and case3_blocked and case4_clean and case5_clean

    metrics = {
        "case1_past_date_blocked": {"text": case1["text"], "blocked": case1_blocked},
        "case2_future_date_clean": {"text": case2["text"], "clean": case2_clean},
        "case3_event_withdrawn_blocked": {"text": case3["text"], "blocked": case3_blocked},
        "case4_event_active_clean": {"text": case4["text"], "clean": case4_clean},
        "case5_after_direction_reversed": {"text": case5["text"], "clean": case5_clean},
        "all_correct": all_correct,
    }

    prose = (
        f"Case 1 (absolute date in the past): blocked={case1_blocked}, text={case1['text']!r}. "
        f"Case 2 (absolute date in the future): clean={case2_clean}, text={case2['text']!r}. "
        f"Case 3 ('until' + context affirming the event): blocked={case3_blocked}, text={case3['text']!r}. "
        f"Case 4 ('until' + context contradicting the event): clean={case4_clean}, text={case4['text']!r}. "
        f"Case 5 ('after' + the SAME context that blocked case 3): clean={case5_clean}, text={case5['text']!r} "
        f"-- the identical 'withdrew consent' context blocks an 'until' rule but clears an 'after' rule, "
        f"proving direction genuinely changes the reasoning outcome, not just a detection label."
    )

    conclusion = (
        "Temporal bound reasoning is now a real, second reasoning primitive alongside condition/exception "
        "checking, reachable through brain.reason() itself: absolute dates resolve deterministically against "
        "the real reference time, event-relative bounds resolve via the same bounded NLI judgment check_"
        "exception already uses elsewhere (never duplicated), and direction (until/before vs after/once) "
        "correctly flips which outcome the same context produces -- case 5 is the real proof, not case 1-4 "
        "alone, since it shows the identical context giving the OPPOSITE result for the opposite direction."
        if all_correct
        else "At least one case did not behave as expected -- see metrics, reported as measured."
    )

    run.finish(
        title="Temporal bound reasoning (until/before/after/once): a genuinely new primitive, not a lookup-table entry",
        goal=(
            "Build the reasoning TEMPORAL_BOUND connectives actually need -- an ordering/timing judgment, not "
            "the truth judgment check_exception already provides -- and wire it into brain.reason() through "
            "the same production path condition/exception checking already uses, so a rule's 'until'/'before'/"
            "'after'/'once' clause is no longer silently ignored."
        ),
        method=(
            "lab.common.temporal.find_temporal_bound/check_temporal_bound (new): splits a rule's consequence "
            "at its TEMPORAL_BOUND connective, then resolves the bound clause either deterministically (a "
            "literal date via lab.common.calc.parse_date, already used elsewhere) or via one bounded NLI "
            "judgment (reusing check_exception unchanged) when the clause names an event instead. lab.common."
            "brain._check_rule_gate (new) unifies this with the existing condition/exception gate behind one "
            "interface so both rule-application branches get it automatically. Five cases through reason() "
            "itself, including a direction-reversal case (same context, opposite connective direction, "
            "opposite outcome) as the real proof the mechanism reasons about timing, not just detects words."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "Event-relative resolution depends on the same lexical-NLI-model sensitivity to phrasing every "
            "other NLI-based check in this repo already carries (EXP-088 documented a real near-miss; this "
            "exploration's own fixture sentences were chosen to score clearly on the right side of tau, not "
            "swept across many phrasings). Absolute-date resolution uses real wall-clock 'now' as the default "
            "reference point when none is given -- deterministic for any one run, but this exploration's own "
            "test dates (2020/2030) were chosen with a wide safety margin rather than measuring exactly how "
            "close to 'now' the boundary can get before dateparser's own parsing becomes ambiguous."
        ),
        referenced_files=FILES,
        follow_ups=[
            "No explicit 'reference_date' is threaded through from brain.reason() -- it always defaults to "
            "real wall-clock time. A real document's own 'as of' date (if stated) should override this, not "
            "attempted here.",
        ],
        models_used=(
            "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli via the existing, unmodified check_exception, for "
            "event-relative bounds only. dateparser (already a dependency, lab.common.calc.parse_date, "
            "deterministic) for absolute dates. No generative model."
        ),
    )

    print("case1:", case1_blocked, "case2:", case2_clean, "case3:", case3_blocked, "case4:", case4_clean, "case5:", case5_clean)


if __name__ == "__main__":
    main()
