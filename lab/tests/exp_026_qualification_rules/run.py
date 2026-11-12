"""EXP-026: qualification rules for except, unless, and provided that --
the repo's oldest open todo stub for this gap, closed properly rather than
patched on top of.

The stub's own one-line goal ("Add code rules for except, unless, and
provided that if the lexical judge keeps missing them") would have been
WRONG to implement literally: "unless"/"except"/"except that" and
"provided that" are not the same kind of clause. lab.common.connectives'
Operator table (EXP-090) already names the real distinction --
CONDITION_NEGATIVE (unless/except) blocks its main clause if its own
clause is TRUE; CONDITION_POSITIVE (provided that/only if/as long as/in
case) blocks its main clause if its own clause is FALSE, the opposite
polarity. Treating all three identically (as the stub's wording implies)
would have derived the wrong answer for "provided that" half the time.

What closes this for real (lab/common/inference.py, this session):
  - split_exception/split_exceptions now detect BOTH polarities via
    find_connectives, not just CONDITION_NEGATIVE (EXP-091's own scope).
  - check_exceptions takes the detected polarity and applies the mirrored
    combination rule: negative blocks on any-alternative-holds, positive
    blocks only when EVERY alternative is confirmed false.
  - Two more hardcoded keyword regexes were found and removed in the same
    pass, both the exact class of hardcoding the project owner ruled out:
    _EXCEPTION_ALT_RE's `(?:or\\s+)?` (a literal match on the word "or"
    when stripping a trailing alternative's leading combinator) and
    _clauses' `r"\\band\\b"` (a literal match on "and" that would have
    also wrongly split a non-clausal compound like "the registration and
    license will be suspended" into two meaningless fragments). Both now
    use find_connectives' structural cc/COMBINATOR detection instead.

Four cases through lab.common.brain.reason(ask, passages) itself, the
"provided that" shape never previously reachable at all (not even through
the old _UNLESS_RE code, which only ever recognized the literal word
"unless"):
  1. "provided that" phrasing, context affirms the condition -> the
     consequence derives CLEANLY (positive polarity: condition true means
     proceed, the opposite of what EXP-091's "except" case did).
  2. "provided that" phrasing, context contradicts the condition -> the
     consequence is BLOCKED ("policy does not apply").
  3. "provided that" phrasing, no context at all -> the consequence
     derives but is FLAGGED unresolved (same honest-abstention posture as
     the negative-polarity case, mirrored).
  4. A compound-subject consequence with a non-clausal "and"
     ("the registration and license will be suspended") -> instantiate_
     consequence must NOT shred it into two fragments, regression-proving
     the new structural _clauses split against the exact failure mode the
     old regex would have hit.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run
from lab.common.inference import _clauses

FILES = [
    "lab/tests/exp_026_qualification_rules/run.py",
    "lab/common/inference.py",
    "lab/common/connectives.py",
    "lab/common/brain.py",
]

FACT_TEXT = "MedCorp processed Aisha."
ASK = "Does MedCorp's processing of Aisha's data comply with the rule?"
CONDITION_TEXT = "the data subject has given explicit consent to the processing of those personal data for one or more specified purposes"

RULE_PROVIDED = {"id": "rule-provided", "text": f"If anyone processes special category data, it is lawful, provided that {CONDITION_TEXT}."}
FACT_PASSAGE = {"id": "fact-1", "text": FACT_TEXT}
CONDITION_HOLDS_PASSAGE = {"id": "context-holds", "text": f"{CONDITION_TEXT[0].upper()}{CONDITION_TEXT[1:]}."}
CONDITION_CONTRADICTED_PASSAGE = {"id": "context-contradicted", "text": "Aisha never gave any consent at all for this processing."}


def main():
    run = Run("EXP-026", "exp_026_qualification_rules")

    case1 = reason(ASK, [RULE_PROVIDED, FACT_PASSAGE, CONDITION_HOLDS_PASSAGE])
    case1_clean = case1["decision"] == "supported" and "Therefore" in case1["text"] and "policy does not apply" not in case1["text"]

    case2 = reason(ASK, [RULE_PROVIDED, FACT_PASSAGE, CONDITION_CONTRADICTED_PASSAGE])
    case2_blocked = "policy does not apply" in case2["text"] and "Therefore" not in case2["text"]

    case3 = reason(ASK, [RULE_PROVIDED, FACT_PASSAGE])
    case3_flagged = case3["decision"] == "supported_with_flags" and "unresolved" in case3["text"]

    compound_subject = "the registration and license will be suspended"
    case4_clauses = _clauses(compound_subject)
    case4_correct = case4_clauses == [compound_subject]

    run.write_json(
        "cases.json",
        {
            "case1_positive_condition_holds": case1,
            "case2_positive_condition_blocked": case2,
            "case3_positive_condition_unresolved": case3,
            "case4_non_clausal_and_not_split": {"input": compound_subject, "clauses": case4_clauses},
        },
    )

    all_correct = case1_clean and case2_blocked and case3_flagged and case4_correct

    metrics = {
        "case1_positive_condition_holds": {"decision": case1["decision"], "text": case1["text"], "clean": case1_clean},
        "case2_positive_condition_blocked": {"decision": case2["decision"], "text": case2["text"], "blocked": case2_blocked},
        "case3_positive_condition_unresolved": {"decision": case3["decision"], "text": case3["text"], "flagged": case3_flagged},
        "case4_non_clausal_and_not_split": {"clauses": case4_clauses, "correct": case4_correct},
        "all_correct": all_correct,
    }

    prose = (
        f"Case 1 ('provided that' phrasing, condition affirmed): decision='{case1['decision']}', text="
        f"{case1['text']!r} -- clean={case1_clean}. Case 2 (condition contradicted): decision='{case2['decision']}', "
        f"text={case2['text']!r} -- blocked={case2_blocked}. Case 3 (no context): decision='{case3['decision']}', "
        f"text={case3['text']!r} -- flagged={case3_flagged}. Case 4 (a non-clausal 'and', 'the registration and "
        f"license will be suspended'): _clauses returned {case4_clauses!r} -- correct={case4_correct} (the old "
        f"r'\\band\\b' regex would have returned ['the registration', 'license will be suspended'], two meaningless "
        f"fragments)."
    )

    conclusion = (
        "EXP-026's real gap -- 'except'/'unless'/'provided that' clauses invisible to the engine -- is closed, "
        "but not by treating all three the same, which the stub's own wording would have gotten wrong: "
        "'provided that' is the opposite polarity from 'unless'/'except' (EXP-091), and check_exceptions now "
        "applies the correct mirrored combination rule for each. Two further hardcoded keyword regexes "
        "(the alternative-splitter's literal 'or' match, and _clauses' literal 'and' match) were found and "
        "replaced with the same structural find_connectives detection in the same pass, closing the same class "
        "of gap EXP-090/091 closed for 'unless', not just the one instance already flagged."
        if all_correct
        else "At least one case did not behave as expected -- see metrics for exactly which, reported as measured."
    )

    run.finish(
        title="Qualification rules for except/unless/provided-that, closed as two opposite-polarity condition classes, not one",
        goal=(
            "Close the repo's oldest open todo for 'except'/'unless'/'provided that' qualification clauses -- "
            "correctly, which the stub's own wording (treat all three the same) would not have done. Generalize "
            "lab.common.inference's exception mechanism to recognize CONDITION_POSITIVE (provided that/only if/as "
            "long as/in case) alongside the existing CONDITION_NEGATIVE (unless/except/except that), with the "
            "correct mirrored blocking rule for each, and remove two further hardcoded keyword regexes found "
            "while doing it: the alternative-splitter's literal 'or' match and _clauses' literal 'and' match."
        ),
        method=(
            "lab.common.inference.split_exception/split_exceptions generalized to detect either "
            "Operator.CONDITION_NEGATIVE or CONDITION_POSITIVE via find_connectives and return the detected "
            "polarity; check_exceptions takes that polarity and applies the mirrored OR-combination rule "
            "(negative: any-holds blocks; positive: all-confirmed-false blocks). The alternative-splitter's "
            "literal regex match on 'or' and _clauses' literal regex match on 'and' were both replaced with "
            "find_connectives-based structural detection. Four cases through lab.common.brain.reason/_clauses "
            "directly, re-running the full EXP-083/085/088/089/091 regression suite first to confirm zero "
            "behavior change for every existing 'unless'/'except' case."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "Only CONDITION_POSITIVE's holds-blocks-if-false semantics is wired, matching CONDITION_NEGATIVE's "
            "existing scope -- CONCESSION/TEMPORAL_BOUND/CAUSAL remain detection-only, per EXP-090's own "
            "follow_ups, untouched here. A third hardcoded word-regex was found (lab/common/intent_signals.py's "
            "_CLAUSE_SPLIT_RE, `r\"[?.;]|\\band\\b\"`, used for splitting an ASK into clauses for the document/"
            "identity/total intent signals) but deliberately NOT changed in this exploration -- it is load-"
            "bearing for calibrated thresholds across EXP-069/078/079, and fixing it needs its own regression "
            "pass against those, not a drive-by edit inside this one."
        ),
        referenced_files=FILES,
        follow_ups=[
            "lab/common/intent_signals.py's _CLAUSE_SPLIT_RE has the identical hardcoded `\\band\\b` pattern -- "
            "a real, named instance of the same gap, left open because changing it requires reverifying EXP-069's "
            "calibrated MIN_DENSE_SCORE/MIN_SEMANTIC_MARGIN thresholds and EXP-078/079's document-signal scores, "
            "not just the split logic itself.",
        ],
        models_used=(
            "spaCy en_core_web_sm dependency parser via lab.common.connectives.find_connectives (already built "
            "in EXP-090, unchanged here) plus the existing, unmodified MoritzLaurer/DeBERTa-v3-base-mnli-fever-"
            "anli NLI call inside check_exception. No new model, no generative model."
        ),
    )

    print("case1_clean:", case1_clean, "case2_blocked:", case2_blocked, "case3_flagged:", case3_flagged, "case4_correct:", case4_correct)


if __name__ == "__main__":
    main()
