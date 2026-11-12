"""EXP-083: multi-step symbolic inference, the project owner's own
proposal (verbatim): "rohan killed arun, principle got from rag or from
user is if anyone kills another person is crime and he will go to jail.
convert all in logical expression ... than do multi step thinking."

Measures lab.common.inference.forward_chain on five cases, each proving
a specific, named claim rather than a vague "it works":
  1. The exact motivating example: one rule, one fact, two derived
     consequences (crime, jail), both correctly bound to the actual
     named person, not left as an unbound "he"/"it".
  2. Genuine multi-step chaining: a second rule ("if a person goes to
     jail, their license will be suspended") fires off the FIRST rule's
     own derived fact, not the original one -- proving this is a real
     fixpoint loop, not a single hop relabeled. Also the case that found
     and fixed a real bug: a possessive-pronoun subject ("their
     license") was first bound to the wrong entity ("license" itself,
     not Rohan) until lab.common.inference._extract_clause_predicate
     was taught to resolve it.
  3. An exception whose truth is unresolved (no context given either
     way): the engine must still derive the consequence -- the fact
     that a defense exists in principle doesn't mean it was raised --
     but mark it `conditional=True`, visibly different from case 1's
     clean derivation, never silently equivalent to it.
  4. The same exception, now affirmed by context (self-defense stated
     outright): the consequence must be suppressed entirely, not
     derived-but-flagged.
  5. The same exception, now explicitly contradicted by context: the
     consequence must be derived cleanly (conditional=False), proving
     the engine doesn't default to "unresolved" just because an
     exception clause exists on the rule, only when the evidence
     actually is silent.

No generative model anywhere in this mechanism -- the project owner's
own explicit requirement, stated directly: language-to-rule conversion
must happen through a non-generative model to avoid hallucinating a
rule or a fact that was never actually said. Every extraction step is
spaCy's dependency parser (already a project dependency, lab.common.
rules' own parser); every exception judgment is the real DeBERTa-v3
MNLI classifier (lab.common.real_encoders), one bounded entailment
check, not a generative model's free-text judgment.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.inference import forward_chain
from lab.common.rules import extract_fact_triple, parse_conditional_rule
from lab.tests.fixtures_support import signature_set as _signature_set

FILES = [
    "lab/tests/exp_083_symbolic_inference/run.py",
    "lab/common/inference.py",
    "lab/common/rules.py",
    "data/exp_057_rule_application/results.json",
    "data/exp_059_cross_domain_rules/results.json",
    "data/exp_061_semantic_rule_matching/results.json",
    "data/exp_083_symbolic_inference/results.json",
    "lab/tests/fixtures_support.py",

]

FACT_TEXT = "Rohan killed Arun."
RULE_TEXT = "If anyone kills another person, it is a crime and he will go to jail."
CHAIN_RULE_TEXT = "If a person goes to jail, their license will be suspended."
EXCEPTION_RULE_TEXT = "If a person kills another person, it is a crime, unless it was self-defense."


def main():
    run = Run("EXP-083", "exp_083_symbolic_inference")

    fact = extract_fact_triple(FACT_TEXT)
    rule = parse_conditional_rule(RULE_TEXT)
    chain_rule = parse_conditional_rule(CHAIN_RULE_TEXT)
    exception_rule = parse_conditional_rule(EXCEPTION_RULE_TEXT)

    case1 = forward_chain([fact], [rule])
    case1_sigs = _signature_set(case1["facts"])
    case1_correct = ("Rohan", "be", "a crime") in case1_sigs and ("Rohan", "go", "jail") in case1_sigs

    case2 = forward_chain([fact], [rule, chain_rule], max_steps=5)
    case2_sigs = _signature_set(case2["facts"])
    case2_correct = ("Rohan", "suspend", "their license") in case2_sigs and case2["steps"] == 3

    case3 = forward_chain([fact], [exception_rule], context_texts=[])
    case3_derived = [f for f in case3["facts"] if f.get("derivation")]
    case3_correct = len(case3_derived) == 1 and case3_derived[0]["conditional"] is True and case3_derived[0]["derivation"]["exception_check"]["status"] == "unknown"

    case4 = forward_chain([fact], [exception_rule], context_texts=["Rohan acted in self-defense when he killed Arun."])
    case4_derived = [f for f in case4["facts"] if f.get("derivation")]
    case4_correct = len(case4_derived) == 0

    case5 = forward_chain([fact], [exception_rule], context_texts=["It was not self-defense; Rohan attacked Arun without provocation."])
    case5_derived = [f for f in case5["facts"] if f.get("derivation")]
    case5_correct = len(case5_derived) == 1 and case5_derived[0]["conditional"] is False

    run.write_json(
        "cases.json",
        {
            "case1_single_hop": case1,
            "case2_multi_hop_chain": case2,
            "case3_exception_unresolved": case3,
            "case4_exception_holds": case4,
            "case5_exception_not_holds": case5,
        },
    )

    all_correct = case1_correct and case2_correct and case3_correct and case4_correct and case5_correct

    metrics = {
        "case1_single_hop": {"correct": case1_correct, "derived_facts": sorted(case1_sigs - {("Rohan", "kill", "Arun")})},
        "case2_multi_hop_chain": {"correct": case2_correct, "steps": case2["steps"], "derived_facts": sorted(case2_sigs - {("Rohan", "kill", "Arun")})},
        "case3_exception_unresolved": {"correct": case3_correct, "status": case3_derived[0]["derivation"]["exception_check"]["status"] if case3_derived else None, "conditional": case3_derived[0]["conditional"] if case3_derived else None},
        "case4_exception_holds": {"correct": case4_correct, "derived_count": len(case4_derived)},
        "case5_exception_not_holds": {"correct": case5_correct, "conditional": case5_derived[0]["conditional"] if case5_derived else None},
        "all_correct": all_correct,
    }

    prose = (
        f"Case 1 (single hop): kill(Rohan, Arun) + the rule derived {metrics['case1_single_hop']['derived_facts']} "
        f"-- correct={case1_correct}. Case 2 (3-step chain, kill -> crime+jail -> license suspended): derived "
        f"{metrics['case2_multi_hop_chain']['derived_facts']} in {case2['steps']} rounds -- correct={case2_correct} "
        f"(this case caught and fixed a real possessive-pronoun subject-binding bug before this run). Case 3 "
        f"(exception exists, no context either way): derived the consequence but marked conditional=True, status="
        f"'{metrics['case3_exception_unresolved']['status']}' -- correct={case3_correct}. Case 4 (context affirms "
        f"the exception): {metrics['case4_exception_holds']['derived_count']} facts derived (consequence "
        f"correctly suppressed) -- correct={case4_correct}. Case 5 (context contradicts the exception): derived "
        f"cleanly with conditional={metrics['case5_exception_not_holds']['conditional']} -- correct={case5_correct}."
    )

    conclusion = (
        "Multi-step symbolic inference -- converting a stated rule and a stated fact into predicate form, "
        "unifying the trigger, binding the consequence's subject to the actual named entity, and chaining a "
        "derived fact into further rules until nothing new follows -- works as a real mechanism, not just on "
        "the single-hop case this project already had (EXP-057/059/061), but genuinely across multiple steps. "
        "The exception handling is the part that matters most for trust: an exception whose truth the given "
        "context never actually states is never silently treated as false, only as unresolved and visibly "
        "flagged, and a rule with no stated exception at all is never confused with one whose exception just "
        "happens to not apply here. Every step runs through spaCy's dependency parser or the real DeBERTa-v3 "
        "NLI classifier -- no generative model anywhere in the conversion from language to rule/fact form, the "
        "project owner's own explicit requirement, so nothing in this chain can hallucinate a predicate that "
        "was never actually stated."
        if all_correct
        else "At least one case did not behave as expected -- see metrics for exactly which, reported as "
        "measured, not assumed to work."
    )

    run.finish(
        title="Multi-step symbolic inference: rule+fact to predicates, forward-chained, with honest exception handling",
        goal=(
            "Prove the project owner's own proposal -- convert a stated rule and a stated fact into logical/"
            "predicate form and let deterministic code chain the consequences across multiple steps, entirely "
            "without a generative model -- on the exact motivating example (Rohan/Arun), a genuine multi-step "
            "chain, and an exception clause in all three of its honest states (unresolved, holds, does not "
            "hold)."
        ),
        method=(
            "lab.common.rules.extract_fact_triple/parse_conditional_rule (existing, unmodified) extract the "
            "fact and rule; lab.common.inference.instantiate_consequence turns a matched rule's consequence "
            "into new predicate(s) bound to the triggering entity; forward_chain repeatedly applies every rule "
            "to every known fact (including newly derived ones) until a round derives nothing new. Five cases: "
            "single hop, a 3-step chain through a second rule, and the same exception-bearing rule run with no "
            "context, context affirming the exception, and context contradicting it."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="Five hand-built cases proving each named mechanism works, not a broad benchmark across many rules or a real multi-exception statute (GDPR Art 9's four exceptions) -- that combination is a named follow-up, not covered here.",
        referenced_files=FILES,
        follow_ups=[
            "Not yet tested on a rule with more than one exception combined by OR (GDPR Art 9's actual shape: four listed exceptions, any one of which blocks the prohibition) -- split_exception only handles a single trailing 'unless' clause, not a disjunction of several.",
            "_extract_clause_predicate's possessive-subject fix (case 2) was found on exactly one example ('their license will be suspended') -- worth testing on other possessive shapes ('his bail will be denied', 'her assets will be seized') before trusting it generalizes, the same caution EXP-082 learned the hard way about hand-tuning against one fixture.",
            "check_exception's NLI call reads the whole context sentence as one premise; a longer passage with the exception's evidence buried in one clause among many was not tested -- EXP-056/069's sentence-splitting approach for ask-relevance may be needed here too if this scales to real documents.",
            "Not yet wired into lab.common.brain.reason as a signal -- this module is callable standalone, the same gap lab.common.longform had before EXP-079 wired it in.",
        ],
        models_used="spaCy en_core_web_sm dependency parser (fact/rule/consequence extraction, non-generative, deterministic) + MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli (exception entailment, one bounded judgment per check, non-generative). No generative model anywhere in this exploration.",
    )

    print("case1:", case1_correct, "case2:", case2_correct, "case3:", case3_correct, "case4:", case4_correct, "case5:", case5_correct)


if __name__ == "__main__":
    main()
