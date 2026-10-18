"""EXP-091: wire EXP-090's grammar-driven connective detector into
lab.common.inference, closing the gap EXP-090 claimed but never actually
made -- its own title said "replacing the hardcoded 'unless' regex", but
lab.common.inference.split_exception kept calling `_UNLESS_RE` (a literal
regex on the single word "unless") the whole time. lab.common.connectives.
find_connectives existed, was measured, and sat completely unused by the
one module it was built to fix.

Verified directly before this exploration, with the OLD code still in
place:
    split_exceptions("it is unlawful except the data subject has given "
                      "explicit consent")
    -> ("it is unlawful except the data subject has given explicit "
        "consent", [])
The exception clause is invisible. A rule phrased with "except" instead of
"unless" -- real statutory English, GDPR itself uses it -- would fire its
consequence with NO exception check at all: confidently wrong, not merely
untested.

The fix (lab/common/inference.py): split_exception now calls
find_connectives(consequence) and looks for a match whose operator is
Operator.CONDITION_NEGATIVE (unless / except / except that -- the only
connective class with established holds-blocks reasoning semantics so
far; EXP-090's own follow_ups named CONCESSION/TEMPORAL_BOUND/CAUSAL as
separate, later work, not touched here). The match's own anchor_text (its
exact surface form) locates the split point in the original string -- the
same single-point split the old regex did, just at a position grammar
decided was a genuine subordinating exception connective, not one
hardcoded word. check_exception/check_exceptions/forward_chain/
brain.reason are all unchanged -- this exploration only re-points
split_exception at a different (correct) detector.

Four cases, through lab.common.brain.reason(ask, passages) itself (the one
production entry point, same as EXP-089), not a unit test of
split_exception in isolation:
  1. "unless" phrasing, context states the exception holds -> blocked.
     Regression: must still work exactly as EXP-089 measured.
  2. "except" phrasing (same exception content, same context) -> blocked.
     NEW: this is exactly the case the old _UNLESS_RE silently missed --
     it would have asserted the consequence unconditionally.
  3. "except that" phrasing, context contradicts -> consequence asserted
     cleanly, not flagged.
  4. The real three-alternative GDPR Art 9 rule (EXP-085's RULE_TEXT,
     "unless A; B; or C") -> still splits into exactly 3 alternatives.
     Regression: multi-exception OR-combination must survive the switch
     from regex to grammar-driven detection.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run
from lab.common.inference import split_exceptions
from lab.common.rules import parse_conditional_rule
from lab.exp_085_multi_exception_scoping.run import RULE_TEXT as GDPR_MULTI_EXCEPTION_RULE_TEXT

FILES = [
    "lab/exp_091_connective_wiring/run.py",
    "lab/common/inference.py",
    "lab/common/connectives.py",
    "lab/common/brain.py",
    "lab/common/rules.py",
    "lab/exp_085_multi_exception_scoping/run.py",
    "lab/exp_090_connective_detection/run.py",
]

FACT_TEXT = "MedCorp processed Aisha."
ASK = "Does MedCorp's processing of Aisha's data comply with the rule, or does an exception apply?"

CONSENT_TEXT = "the data subject has given explicit consent to the processing of those personal data for one or more specified purposes"

RULE_UNLESS = {"id": "rule-unless", "text": f"If anyone processes special category data, it is unlawful, unless {CONSENT_TEXT}."}
RULE_EXCEPT = {"id": "rule-except", "text": f"If anyone processes special category data, it is unlawful, except {CONSENT_TEXT}."}
RULE_EXCEPT_THAT = {"id": "rule-except-that", "text": "If anyone processes special category data, it is unlawful, except that explicit consent removes the prohibition."}
FACT_PASSAGE = {"id": "fact-1", "text": FACT_TEXT}
CONSENT_HOLDS_PASSAGE = {"id": "context-holds", "text": f"{CONSENT_TEXT[0].upper()}{CONSENT_TEXT[1:]}."}
CONSENT_CONTRADICTED_PASSAGE = {"id": "context-contradicted", "text": "Aisha never gave any consent at all for this processing."}


def main():
    run = Run("EXP-091", "exp_091_connective_wiring")

    case1 = reason(ASK, [RULE_UNLESS, FACT_PASSAGE, CONSENT_HOLDS_PASSAGE])
    case1_blocked = "policy does not apply" in case1["text"] and "Therefore" not in case1["text"]

    case2 = reason(ASK, [RULE_EXCEPT, FACT_PASSAGE, CONSENT_HOLDS_PASSAGE])
    case2_blocked = "policy does not apply" in case2["text"] and "Therefore" not in case2["text"]

    case3 = reason(ASK, [RULE_EXCEPT_THAT, FACT_PASSAGE, CONSENT_CONTRADICTED_PASSAGE])
    case3_clean = case3["decision"] == "supported" and "unresolved" not in case3["text"] and "Therefore" in case3["text"]

    gdpr_rule = parse_conditional_rule(GDPR_MULTI_EXCEPTION_RULE_TEXT)
    _, gdpr_alternatives, gdpr_polarity = split_exceptions(gdpr_rule["consequence"])
    case4_correct = len(gdpr_alternatives) == 3 and gdpr_polarity == "negative"

    run.write_json(
        "cases.json",
        {
            "case1_unless_blocked": case1,
            "case2_except_blocked": case2,
            "case3_except_that_clean": case3,
            "case4_gdpr_multi_exception_alternatives": gdpr_alternatives,
        },
    )

    all_correct = case1_blocked and case2_blocked and case3_clean and case4_correct

    metrics = {
        "case1_unless_blocked": {"decision": case1["decision"], "text": case1["text"], "blocked": case1_blocked},
        "case2_except_blocked": {"decision": case2["decision"], "text": case2["text"], "blocked": case2_blocked},
        "case3_except_that_clean": {"decision": case3["decision"], "text": case3["text"], "clean": case3_clean},
        "case4_gdpr_multi_exception": {"n_alternatives": len(gdpr_alternatives), "correct": case4_correct},
        "all_correct": all_correct,
    }

    prose = (
        f"Case 1 ('unless' phrasing, exception holds): decision='{case1['decision']}', text={case1['text']!r} -- "
        f"blocked={case1_blocked}. Case 2 ('except' phrasing, same exception content and context): decision="
        f"'{case2['decision']}', text={case2['text']!r} -- blocked={case2_blocked}. Under the OLD _UNLESS_RE code "
        f"this case would have asserted the consequence unconditionally, since 'except' never matched "
        f"\\bunless\\b. Case 3 ('except that' phrasing, exception contradicted): decision='{case3['decision']}', "
        f"text={case3['text']!r} -- clean={case3_clean}. Case 4 (the real 3-alternative GDPR Art 9 rule from "
        f"EXP-085, still phrased with 'unless A; B; or C'): split into {len(gdpr_alternatives)} alternatives "
        f"(expected 3) -- correct={case4_correct}."
    )

    conclusion = (
        "lab.common.inference.split_exception now locates a rule's exception clause via lab.common.connectives."
        "find_connectives's structural CONDITION_NEGATIVE detection instead of a hardcoded regex on the single "
        "word 'unless'. The gap this closes is not hypothetical: case 2 is the exact failure mode measured "
        "before this change (the 'except' phrasing was silently invisible to the old code), and it is now "
        "caught through brain.reason itself, the one production entry point, with no regression on the "
        "'unless' phrasing (case 1), the 'except that' phrasing (case 3), or the real multi-alternative GDPR "
        "Art 9 rule's OR-combination (case 4)."
        if all_correct
        else "At least one case did not behave as expected -- see metrics for exactly which, reported as measured."
    )

    run.finish(
        title="Wire EXP-090's grammar-driven connective detector into lab.common.inference, replacing _UNLESS_RE for real",
        goal=(
            "EXP-090 built and measured lab.common.connectives.find_connectives but never actually called it "
            "from lab.common.inference.py -- _UNLESS_RE was still the only thing split_exception ran, despite "
            "EXP-090's own title claiming the replacement happened. Replace it for real: split_exception finds "
            "the exception clause via find_connectives's CONDITION_NEGATIVE detection (unless/except/except "
            "that), and prove the case the old regex silently missed ('except' phrasing) is now caught through "
            "brain.reason itself, with no regression on the existing 'unless' and multi-alternative cases."
        ),
        method=(
            "lab.common.inference.split_exception rewritten to call find_connectives(consequence), filter to "
            "Operator.CONDITION_NEGATIVE matches, and split the original string at the first match's own "
            "anchor_text -- the same single-point split the old regex did, now at a position grammar decided "
            "was a genuine exception connective. check_exception/check_exceptions/forward_chain/brain.reason "
            "are unchanged. Four cases through reason(ask, passages) directly: 'unless' (regression), 'except' "
            "(the gap), 'except that' (a second previously-unreachable phrase), and the real GDPR Art 9 "
            "3-alternative rule (regression for OR-combination)."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "Only CONDITION_NEGATIVE is wired -- CONCESSION (although/though/despite), TEMPORAL_BOUND "
            "(until/before/after), and CAUSAL (because/since) still have zero reasoning semantics in "
            "check_exceptions/forward_chain; EXP-090 named this split explicitly and it is not revisited here. "
            "The threshold-rule branch in brain.py (apply_threshold_rule) still never calls split_exceptions/ "
            "check_exceptions at all -- a separate, already-named gap, untouched by this change."
        ),
        referenced_files=FILES,
        follow_ups=[
            "Wire CONCESSION's opposite polarity (holds ANYWAY, never blocks) into check_exceptions/"
            "forward_chain -- the next connective class with a well-defined semantics, per EXP-090's own "
            "follow_ups.",
            "Give the threshold-rule branch in brain.py the same split_exceptions/check_exceptions call the "
            "verb-rule branch now has, for a threshold rule whose consequence carries an exception clause.",
        ],
        models_used=(
            "spaCy en_core_web_sm dependency parser via lab.common.connectives.find_connectives (already built "
            "in EXP-090, unchanged here) plus the existing, unmodified MoritzLaurer/DeBERTa-v3-base-mnli-fever-"
            "anli NLI call inside check_exception. No new model, no generative model."
        ),
    )

    print("case1_unless_blocked:", case1_blocked, "case2_except_blocked:", case2_blocked, "case3_clean:", case3_clean, "case4_alternatives:", len(gdpr_alternatives))


if __name__ == "__main__":
    main()
