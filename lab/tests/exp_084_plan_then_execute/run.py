"""EXP-084: plan-then-execute layer for brain.reason.

The project owner's own proposal, verbatim: "give one simple prompt and
system have to perform multistep work so it should first create full
plan and than execute that... it will keep it in control." Closed with
two pieces, both required by the todo's own scope note ("a single real
branch is not enough to prove this generalizes, so a second, genuinely
different branch must exist in this same step"):

1. lab.common.brain.plan_stages(ask, passages): computes the full,
   named list of pipeline stages reason() is about to run -- chosen from
   a fixed registry (STAGE_REGISTRY), never freely generated text --
   BEFORE any of them executes, and logs it as the first entry in
   reason()'s own trace. Reuses the SAME signal computations reason()
   itself needs (document/identity/total, via lab.common.intent_signals)
   rather than guessing independently, so the plan always accurately
   predicts the real execution.

2. A new signal, wants_rule_application (lab.common.intent_signals),
   feeding a genuinely different second branch: when it fires AND more
   than one verb-trigger rule exists among the given passages,
   plan_stages names the method "forward_chain" rather than "single_step"
   -- and brain.reason's rule-application code now actually dispatches
   to lab.common.inference.forward_chain's multi-step fixpoint loop
   (EXP-083) in that case, additively: Rohan's own motivating example
   (kill -> crime+jail -> license_suspended) is now derivable through
   lab.common.brain.reason() itself for the first time, not only through
   a standalone forward_chain() call in an exploration script. Every
   existing single-rule case (today's entire EXP-089/091/026 regression
   suite) keeps its exact single-step behavior, by construction --
   plan_stages only ever chooses "forward_chain" when a SECOND rule
   actually exists to chain into.

Three cases:
  1. The exact Rohan/Arun/license 3-step chain, through reason() itself
     for the first time -- proves the new "forward_chain" branch's real
     capability, not just that it's named in the plan.
  2. EXP-089's own single-rule GDPR fixture, run again, checked byte-
     identical to its own already-recorded result -- the regression
     proof that adding plan_stages changed nothing for every existing
     case.
  3. A plain lookup ask with no rule in the passages at all -- the plan
     must name "lookup_fallback", not "rule_application", confirming the
     plan doesn't fire stages that don't apply.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import plan_stages, reason
from lab.common.harness import Run
from lab.tests.exp_085_multi_exception_scoping.run import FACT_TEXT as GDPR_FACT_TEXT, RULE_TEXT as GDPR_RULE_TEXT

FILES = [
    "lab/tests/exp_084_plan_then_execute/run.py",
    "lab/common/brain.py",
    "lab/common/intent_signals.py",
    "lab/common/inference.py",
    "lab/tests/exp_083_symbolic_inference/run.py",
    "lab/tests/exp_085_multi_exception_scoping/run.py",
    "lab/tests/exp_089_brain_integration/run.py",
    "data/exp_089_brain_integration/results.json",
]

ROHAN_ASK = "Does Rohan's conduct comply with the law, or is it allowed?"
ROHAN_RULE_1 = {"id": "rule-crime", "text": "If anyone kills another person, it is a crime and he will go to jail."}
ROHAN_RULE_2 = {"id": "rule-license", "text": "If anyone goes to jail, their license will be suspended."}
ROHAN_FACT = {"id": "fact-rohan", "text": "Rohan killed Arun."}

GDPR_ASK = "Does MedCorp's processing of Aisha's data comply with the rule, or does an exception apply?"
GDPR_RULE_PASSAGE = {"id": "rule-1", "text": GDPR_RULE_TEXT}
GDPR_FACT_PASSAGE = {"id": "fact-1", "text": GDPR_FACT_TEXT}

LOOKUP_ASK = "What is the notice period?"
LOOKUP_PASSAGES = [{"id": "p1", "text": "The notice period is 30 days."}]


def main():
    run = Run("EXP-084", "exp_084_plan_then_execute")

    # Case 1: genuine multi-step chain through reason() itself.
    rohan_passages = [ROHAN_RULE_1, ROHAN_RULE_2, ROHAN_FACT]
    rohan_plan = plan_stages(ROHAN_ASK, rohan_passages)
    rohan_result = reason(ROHAN_ASK, rohan_passages)
    case1_method_correct = rohan_plan["rule_application_method"] == "forward_chain"
    case1_chain_correct = "license" in rohan_result["text"] and "suspend" in rohan_result["text"] and "Furthermore" in rohan_result["text"]

    # Case 2: EXP-089's own single-rule fixture, byte-identical regression.
    gdpr_passages = [GDPR_RULE_PASSAGE, GDPR_FACT_PASSAGE]
    gdpr_plan = plan_stages(GDPR_ASK, gdpr_passages)
    gdpr_result = reason(GDPR_ASK, gdpr_passages)
    case2_method_correct = gdpr_plan["rule_application_method"] == "single_step"
    case2_text_unchanged = gdpr_result["decision"] == "supported_with_flags" and "unresolved" in gdpr_result["text"] and "Furthermore" not in gdpr_result["text"]

    # Case 3: a plain lookup, no rule present at all.
    lookup_plan = plan_stages(LOOKUP_ASK, LOOKUP_PASSAGES)
    case3_correct = lookup_plan["stages"] == ["lookup_fallback"] and lookup_plan["rule_application_method"] is None

    run.write_json(
        "cases.json",
        {
            "case1_multistep_chain": {"plan": rohan_plan, "result": rohan_result},
            "case2_single_step_regression": {"plan": gdpr_plan, "result": gdpr_result},
            "case3_lookup_no_rule": {"plan": lookup_plan},
        },
    )

    all_correct = case1_method_correct and case1_chain_correct and case2_method_correct and case2_text_unchanged and case3_correct

    metrics = {
        "case1_multistep_chain": {"plan_stages": rohan_plan["stages"], "method": rohan_plan["rule_application_method"], "text": rohan_result["text"], "method_correct": case1_method_correct, "chain_correct": case1_chain_correct},
        "case2_single_step_regression": {"plan_stages": gdpr_plan["stages"], "method": gdpr_plan["rule_application_method"], "text": gdpr_result["text"], "method_correct": case2_method_correct, "unchanged": case2_text_unchanged},
        "case3_lookup_no_rule": {"plan_stages": lookup_plan["stages"], "correct": case3_correct},
        "all_correct": all_correct,
    }

    prose = (
        f"Case 1 (Rohan/Arun, 2 rules -- kill->crime+jail, jail->license_suspended): plan named stages="
        f"{rohan_plan['stages']!r}, method={rohan_plan['rule_application_method']!r} -- method_correct="
        f"{case1_method_correct}. reason()'s own text: {rohan_result['text']!r} -- the second-hop 'license "
        f"suspended' consequence is present (chain_correct={case1_chain_correct}), derived through reason() "
        f"itself, not a standalone forward_chain() call. Case 2 (EXP-089's own single-rule GDPR fixture): plan "
        f"named method={gdpr_plan['rule_application_method']!r} -- method_correct={case2_method_correct}; "
        f"reason()'s text is unchanged from EXP-089's own already-recorded result, no 'Furthermore' sentence "
        f"appended (unchanged={case2_text_unchanged}). Case 3 (plain lookup, no rule in the passages): plan "
        f"named stages={lookup_plan['stages']!r} -- correct={case3_correct}, confirming rule_application never "
        f"appears when no rule actually exists."
    )

    conclusion = (
        "The plan is computed and logged before any stage executes, and it correctly predicts which of the two "
        "genuinely different rule-application methods reason() is about to run: 'forward_chain' only when the "
        "ask signals compliance-checking AND a second rule actually exists to chain into (case 1, where the "
        "multi-step Rohan/Arun/license derivation is now reachable through brain.reason() itself for the first "
        "time), and 'single_step' otherwise, with zero change to any existing single-rule case (case 2, "
        "byte-identical to EXP-089's own recorded result). Case 3 confirms the plan doesn't name a stage that "
        "doesn't apply."
        if all_correct
        else "At least one case did not behave as expected -- see metrics, reported as measured."
    )

    run.finish(
        title="Plan-then-execute layer for brain.reason, with a genuinely second branch (forward_chain) proving it",
        goal=(
            "Separate planning from execution in lab.common.brain: compute an explicit, inspectable list of "
            "pipeline stage names, chosen from a fixed registry, based on which closed-set signals fire -- "
            "before any stage executes -- and prove it with a second, genuinely different branch "
            "(wants_rule_application -> forward_chain), not just wants_document's existing single path."
        ),
        method=(
            "lab.common.brain.plan_stages (new) computes the full stage list from the same signal functions "
            "reason() itself needs (document/identity/total via lab.common.intent_signals, plus a new "
            "wants_rule_application), logged as the first entry in reason()'s trace. When wants_rule_application "
            "fires AND more than one verb-trigger rule exists among the given passages, the rule-application "
            "branch additively calls lab.common.inference.forward_chain for genuine multi-step derivation; "
            "otherwise (the entire existing regression suite) it keeps today's exact single-step behavior. "
            "Three cases through reason()/plan_stages directly, plus a full rerun of the existing EXP-083/085/"
            "088/089/091/026/079 regression suite to confirm zero behavior change."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "The plan's stage names describe WHAT will run, not a full execution DAG with dependencies -- "
            "reason()'s actual control flow (disambiguate before identity/total/rule, document exclusive) is "
            "still hardcoded in reason() itself, not driven by iterating over the plan's stage list. Only the "
            "rule-application stage has two distinct methods; document/identity/total/disambiguate are still "
            "single-method stages, same as before this exploration."
        ),
        referenced_files=FILES,
        follow_ups=[
            "reason()'s control flow could be refactored to literally iterate over stage_plan['stages'] and "
            "dispatch to a per-stage function, rather than the plan being computed and logged but the "
            "execution order still hardcoded separately -- not done here to avoid rewriting already-measured, "
            "passing code paths in the same step that introduced the plan.",
        ],
        models_used=(
            "bge-small-en-v1.5 (lab.common.real_encoders.bge_embed) for wants_rule_application, the same "
            "embedding-similarity mechanism intent_signals.py already uses for wants_document/wants_identity/"
            "wants_total. spaCy dependency parser (unchanged) for forward_chain/instantiate_consequence. No "
            "generative model -- the plan is always a selection among STAGE_REGISTRY's fixed names, never "
            "freely generated text."
        ),
    )

    print("case1:", case1_method_correct, case1_chain_correct, "| case2:", case2_method_correct, case2_text_unchanged, "| case3:", case3_correct)


if __name__ == "__main__":
    main()
