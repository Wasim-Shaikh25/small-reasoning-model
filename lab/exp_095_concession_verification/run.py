"""EXP-095: verifying CONCESSION already behaves correctly by omission --
the same situation CAUSAL was in before EXP-094 gave it a named
'justification' field.

lab.common.connectives' own docstring: "although"/"though"/"even
though"/"even if"/"despite" are the OPPOSITE of unless/except -- the
main clause holds ANYWAY, regardless of their own clause's truth.
lab.common.inference's _find_condition_match only ever recognizes
Operator.CONDITION_NEGATIVE/CONDITION_POSITIVE; CONCESSION is never
passed to it at all. The question this exploration answers: does that
omission actually produce the correct behavior (the consequence always
proceeds, unaffected by the concession clause either way), or does it
produce some OTHER wrong behavior (silently dropping the concession
text, say, or crashing on it)?

Three cases, same rule+fact, only the CONTEXT passage changes -- if
CONCESSION is truly never a gate, all three must produce IDENTICAL
output, since nothing about the context should matter when the
connective isn't CONDITION_NEGATIVE/POSITIVE at all:
  1. Context affirms the concession's own clause.
  2. Context contradicts the concession's own clause.
  3. No context at all.
Unlike a genuine exception, none of these three should ever differ,
and none should be flagged "unresolved" -- there is nothing to resolve.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/exp_095_concession_verification/run.py",
    "lab/common/brain.py",
    "lab/common/inference.py",
    "lab/common/connectives.py",
]

ASK = "Does MedCorp's processing of Aisha's data comply with the rule?"
RULE_TEXT = "If anyone processes special category data, it is unlawful although the data subject has given explicit consent."
RULE_PASSAGE = {"id": "rule-1", "text": RULE_TEXT}
FACT_PASSAGE = {"id": "fact-1", "text": "MedCorp processed Aisha."}
CONSENT_AFFIRMED = {"id": "context-affirm", "text": "The data subject has given explicit consent."}
CONSENT_CONTRADICTED = {"id": "context-contradict", "text": "Aisha never gave any consent at all."}


def main():
    run = Run("EXP-095", "exp_095_concession_verification")

    case1 = reason(ASK, [RULE_PASSAGE, FACT_PASSAGE, CONSENT_AFFIRMED])
    case2 = reason(ASK, [RULE_PASSAGE, FACT_PASSAGE, CONSENT_CONTRADICTED])
    case3 = reason(ASK, [RULE_PASSAGE, FACT_PASSAGE])

    identical = case1["text"] == case2["text"] == case3["text"]
    all_clean = all(c["decision"] == "supported" and "unresolved" not in c["text"] and "policy does not apply" not in c["text"] for c in (case1, case2, case3))
    derives_consequence = all("Therefore" in c["text"] and "unlawful" in c["text"] for c in (case1, case2, case3))

    run.write_json("cases.json", {"context_affirmed": case1, "context_contradicted": case2, "no_context": case3})

    all_correct = identical and all_clean and derives_consequence

    metrics = {
        "identical_across_all_three_contexts": identical,
        "all_clean_no_unresolved_flag": all_clean,
        "all_derive_the_consequence": derives_consequence,
        "case1_text": case1["text"],
        "case2_text": case2["text"],
        "case3_text": case3["text"],
        "all_correct": all_correct,
    }

    prose = (
        f"Three contexts (concession clause affirmed, contradicted, absent) produce identical output: "
        f"{identical}. All three derive the consequence cleanly with no 'unresolved' flag and no blocking: "
        f"{all_clean}. Case 1 (affirmed): {case1['text']!r}. Case 2 (contradicted): {case2['text']!r}. "
        f"Case 3 (no context): {case3['text']!r}."
    )

    conclusion = (
        "CONCESSION's omission from lab.common.inference's condition-detection (_find_condition_match only "
        "recognizes CONDITION_NEGATIVE/POSITIVE) was already the CORRECT behavior, not an unfixed gap: a "
        "concession clause's own truth value genuinely cannot affect whether the consequence proceeds, by "
        "definition (that is what 'holds anyway' means), so never checking it against any context is exactly "
        "right -- the three cases above are identical because nothing about the context should ever change "
        "the outcome. No code change was needed; this exploration exists to verify that claim empirically "
        "rather than assume it, the same way EXP-094 verified CAUSAL's omission was already safe before "
        "adding its justification field."
        if all_correct
        else "The three contexts did NOT produce identical output, or the consequence was blocked/flagged -- "
        "a real bug, not the expected 'correct by omission' result. See metrics for exactly what differed."
    )

    run.finish(
        title="Verifying CONCESSION already behaves correctly by omission (never a gate, consequence always proceeds)",
        goal=(
            "Confirm, rather than assume, that CONCESSION's absence from lab.common.inference's condition-"
            "detection produces the CORRECT behavior (consequence always proceeds regardless of the "
            "concession clause's truth) and not some other silent failure mode."
        ),
        method=(
            "Same rule+fact through lab.common.brain.reason, varying only the context passage: affirms the "
            "concession clause, contradicts it, or omits it entirely. If CONCESSION is truly never a gate, "
            "all three must produce byte-identical output with no 'unresolved' flag."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "Only one hand-built rule/fact pair tested, with 'although' specifically -- not swept across "
            "'though'/'even though'/'even if'/'despite', though all five share the same CONCESSION operator "
            "and the same _find_condition_match omission, so the same reasoning applies to each."
        ),
        referenced_files=FILES,
        follow_ups=[],
        models_used=(
            "spaCy en_core_web_sm dependency parser via lab.common.connectives.find_connectives (unchanged). "
            "No NLI call needed -- no exception check ever fires for a CONCESSION clause, which is exactly "
            "the point being verified. No generative model."
        ),
    )

    print("identical:", identical, "all_clean:", all_clean, "derives_consequence:", derives_consequence)


if __name__ == "__main__":
    main()
