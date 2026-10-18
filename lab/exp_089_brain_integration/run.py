"""EXP-089: exception-aware rule application wired into brain.reason's one
production entry point.

lab.common.brain.reason already had a rule-application branch (_find_rule
-> apply_rule, the verb-trigger shape) before this exploration -- but
apply_rule only compares the rule's trigger lemma against the fact's own
verb lemma. It has never had any idea a rule's consequence might carry an
"unless" clause at all, so a matched rule's consequence was asserted
unconditionally even when the rule's own text named an exception and the
other given passages plainly stated it holds. EXP-083 and EXP-085 proved
split_exceptions/check_exceptions standalone -- this is the first time
that mechanism is reachable from reason() itself, the single entry point
every other capability in this repo goes through (EXP-081).

The change in lab/common/brain.py is deliberately small: inside the
existing `if applied["matched"]:` branch, split the rule's consequence
into its (possibly OR-combined) exception conditions and check them
against every OTHER given passage as context (the same "exceptions are
global policy text, scanned across every passage" principle _find_rule
already uses) -- then:
  - if an exception holds, the matched rule's consequence is not asserted
    at all; an explanatory "policy does not apply" line is returned
    instead (the same pattern the existing threshold-rule role-mismatch
    branch already used for its own "rule matched but doesn't actually
    apply" case -- not a new convention).
  - if every exception is unresolved, the consequence is still asserted,
    visibly suffixed as unresolved, and the overall decision becomes
    "supported_with_flags" -- the same decision value longform already
    uses for a cross-page contradiction, reused here for the same reason:
    a correct-but-flagged answer must never look identical to a clean one.
  - otherwise (no exception, or confidently ruled out) the consequence is
    asserted cleanly, exactly as it already was before this exploration.

check_exception/check_exceptions themselves are completely unchanged --
this is wiring an existing, already-measured mechanism into an existing
entry point, not a new mechanism.

Three cases, each built from passages alone (no hand-assembled call
sequence) and run through lab.common.brain.reason(ask, passages) itself:
  1. Rule + fact, no other passages at all -- every exception unresolved
     -> consequence still asserted, decision flagged.
  2. Rule + fact + a passage stating the consent exception holds (the
     same near-verbatim sentence EXP-085 measured at entail=0.9941) ->
     consequence suppressed entirely.
  3. Rule + fact + a passage that only contradicts the consent
     alternative (the other two stay unknown) -> consequence asserted
     cleanly, decision not flagged.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run
from lab.exp_085_multi_exception_scoping.run import FACT_TEXT, RULE_TEXT

FILES = [
    "lab/exp_089_brain_integration/run.py",
    "lab/common/brain.py",
    "lab/common/inference.py",
    "lab/common/rules.py",
    "lab/exp_085_multi_exception_scoping/run.py",
]

ASK = "Does MedCorp's processing of Aisha's data comply with the rule, or does an exception apply?"

RULE_PASSAGE = {"id": "rule-1", "text": RULE_TEXT}
FACT_PASSAGE = {"id": "fact-1", "text": FACT_TEXT}
CONSENT_HOLDS_PASSAGE = {
    "id": "context-1",
    "text": "The data subject has given explicit consent to the processing of those personal data for one or more specified purposes.",
}
CONSENT_CONTRADICTED_PASSAGE = {
    "id": "context-2",
    "text": "Aisha never gave any consent at all for this processing.",
}


def main():
    run = Run("EXP-089", "exp_089_brain_integration")

    case1 = reason(ASK, [RULE_PASSAGE, FACT_PASSAGE])
    case1_correct = case1["decision"] == "supported_with_flags" and "unresolved" in case1["text"]

    case2 = reason(ASK, [RULE_PASSAGE, FACT_PASSAGE, CONSENT_HOLDS_PASSAGE])
    case2_blocked = "policy does not apply" in case2["text"] and "Therefore" not in case2["text"]

    case3 = reason(ASK, [RULE_PASSAGE, FACT_PASSAGE, CONSENT_CONTRADICTED_PASSAGE])
    case3_correct = case3["decision"] == "supported" and "unresolved" not in case3["text"] and "Therefore" in case3["text"]

    run.write_json(
        "cases.json",
        {
            "case1_no_context": case1,
            "case2_exception_holds": case2,
            "case3_exception_contradicted": case3,
        },
    )

    all_correct = case1_correct and case2_blocked and case3_correct

    metrics = {
        "case1_no_context": {"decision": case1["decision"], "text": case1["text"], "correct": case1_correct},
        "case2_exception_holds": {"decision": case2["decision"], "text": case2["text"], "blocked": case2_blocked},
        "case3_exception_contradicted": {"decision": case3["decision"], "text": case3["text"], "correct": case3_correct},
        "all_correct": all_correct,
    }

    prose = (
        f"Case 1 (rule+fact, no other passages): decision='{case1['decision']}', text={case1['text']!r} -- "
        f"correct={case1_correct}. Case 2 (+ a passage stating the consent exception holds): decision="
        f"'{case2['decision']}', text={case2['text']!r} -- consequence blocked={case2_blocked}. Case 3 (+ a "
        f"passage contradicting only the consent alternative): decision='{case3['decision']}', text="
        f"{case3['text']!r} -- correct={case3_correct}."
    )

    conclusion = (
        "The exception-aware rule-application path is now reachable from lab.common.brain.reason itself, not "
        "only from a standalone forward_chain call: an unresolved exception derives the consequence but flags "
        "the overall decision (supported_with_flags), a confirmed exception suppresses the consequence entirely "
        "and returns an explanatory non-applicability line instead of asserting it, and a confidently ruled-out "
        "exception derives cleanly with no flag -- all three reachable by passing plain passages through the "
        "one entry point every other capability already goes through, with no hand-assembled call sequence."
        if all_correct
        else "At least one case did not behave as expected through reason() itself -- see metrics for exactly "
        "which, reported as measured."
    )

    run.finish(
        title="Exception-aware rule application wired into brain.reason's one production entry point",
        goal=(
            "Close the gap EXP-083/085 both named as a follow-up: the exception-aware multi-exception OR-"
            "combination mechanism they proved standalone was never reachable from lab.common.brain.reason, "
            "the single entry point every other capability in this repo goes through. Wire it into reason()'s "
            "existing verb-rule branch and prove all three of its honest states (unresolved -> flagged; holds "
            "-> suppressed; ruled out -> clean) are reachable by passing plain passages through reason() alone, "
            "not by calling forward_chain directly."
        ),
        method=(
            "lab.common.brain.reason's existing `if applied['matched']:` branch (verb-trigger rule shape) now "
            "calls lab.common.inference.split_exceptions/check_exceptions (both unchanged, proven in EXP-085) "
            "against every other given passage as context before asserting the rule's consequence. "
            "decision='supported_with_flags' (already used by the longform cross-page-contradiction path) is "
            "reused for an unresolved exception; a held exception suppresses the consequence and returns an "
            "explanatory line instead, the same pattern the existing threshold-rule role-mismatch branch "
            "already used. Three cases, same rule/fact fixture as EXP-085, run through reason(ask, passages) "
            "directly."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "Only the verb-trigger rule shape (parse_conditional_rule) is wired -- the threshold-rule branch "
            "(parse_threshold_rule/apply_threshold_rule) does not go through split_exceptions/check_exceptions "
            "at all and is unaffected by this exploration, a real and separate gap if a threshold rule's own "
            "consequence ever carries an 'unless' clause. Three hand-built cases through reason(), not a broad "
            "test across many rule/passage combinations."
        ),
        referenced_files=FILES,
        follow_ups=[
            "The threshold-rule branch (apply_threshold_rule) still has no exception awareness at all -- a "
            "separate, smaller follow-up if a threshold rule's consequence is ever found with an 'unless' "
            "clause in a real document.",
            "Not tested combined with the other reason() signals (identity/total/document) firing at the same "
            "time as the rule branch on the same ask -- only the rule branch's own behavior was exercised here.",
        ],
        models_used=(
            "Same as EXP-083/085: spaCy dependency parser (unchanged) + MoritzLaurer/DeBERTa-v3-base-mnli-"
            "fever-anli via the existing, unmodified check_exception/check_exceptions. No generative model, no "
            "new dependency -- this exploration only wires existing, already-measured pieces into reason()."
        ),
    )

    print("case1:", case1_correct, "case2_blocked:", case2_blocked, "case3:", case3_correct)


if __name__ == "__main__":
    main()
