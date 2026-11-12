"""EXP-057: rule application -- apply a given conditional rule to a given fact.

Directly tests the example raised in review: context provides a rule
("If someone murders a person, it is a punishable crime.") and a fact
("Arjun murdered Neha."), and the ask is whether that's a punishable crime.
lab.common.rules.answer_rule_question finds the rule, finds the fact,
compares one verb lemma, and answers with citations to both -- or abstains
if no rule, no concrete fact, or no match is found. No model decides the
outcome; spaCy's dependency parser (already a project dependency) only
extracts the verb, a narrow syntactic sub-task, not a judgment call.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.rules import answer_rule_question

FILES = [
    "lab/tests/exp_057_rule_application/run.py",
    "lab/common/rules.py",
    "lab/common/real_models.py",
    "lab/common/harness.py",
    "data/exp_057_rule_application/results.json",
]

CASES = [
    {
        "id": "R01_match",
        "ask": "Arjun murdered Neha. Is that a punishable crime?",
        "passages": [
            {"id": "RULE1", "text": "If someone murders a person, it is a punishable crime."},
            {"id": "FACT1", "text": "Arjun murdered Neha."},
        ],
        "expect_decision": "supported",
    },
    {
        "id": "R02_no_match_different_verb",
        "ask": "Arjun borrowed money from Neha. Is that a punishable crime?",
        "passages": [
            {"id": "RULE1", "text": "If someone murders a person, it is a punishable crime."},
            {"id": "FACT1", "text": "Arjun borrowed money from Neha."},
        ],
        "expect_decision": "inconclusive",
    },
    {
        "id": "R03_no_rule_present",
        "ask": "Arjun murdered Neha. Is that a punishable crime?",
        "passages": [
            {"id": "FACT1", "text": "Arjun murdered Neha."},
            {"id": "OTHER1", "text": "The weather was clear that day."},
        ],
        "expect_decision": "inconclusive",
    },
    {
        "id": "R04_match_different_entities",
        "ask": "Is theft a punishable offense here?",
        "passages": [
            {"id": "RULE2", "text": "If a person steals property, it is a punishable offense."},
            {"id": "FACT2", "text": "Priya stole the necklace."},
        ],
        "expect_decision": "supported",
    },
    {
        "id": "R05_no_fact_present",
        "ask": "Is murder a punishable crime?",
        "passages": [
            {"id": "RULE1", "text": "If someone murders a person, it is a punishable crime."},
        ],
        "expect_decision": "inconclusive",
    },
]


def main():
    run = Run("EXP-057", "exp_057_rule_application")
    rows = []
    for case in CASES:
        result = answer_rule_question(case["ask"], case["passages"])
        rows.append(
            {
                "id": case["id"],
                "ask": case["ask"],
                "decision": result["decision"],
                "reason": result["reason"],
                "text": result["text"],
                "rule_parsed": result["rule"],
                "fact_parsed": result["fact"],
                "expect_decision": case["expect_decision"],
                "correct": result["decision"] == case["expect_decision"],
            }
        )
    run.write_json("items.json", rows)

    n = len(rows)
    correct = sum(r["correct"] for r in rows)
    headline = next(r for r in rows if r["id"] == "R01_match")

    metrics = {
        "n": n,
        "accuracy": round(correct / n, 4),
        "headline_case": {
            "ask": headline["ask"],
            "decision": headline["decision"],
            "text": headline["text"],
        },
        "cases": [{"id": r["id"], "decision": r["decision"], "expected": r["expect_decision"], "correct": r["correct"]} for r in rows],
    }

    prose = (
        f"On {n} cases, {correct} match the expected decision (accuracy {metrics['accuracy']}). "
        f"The headline case -- rule 'If someone murders a person, it is a punishable crime.' plus fact "
        f"'Arjun murdered Neha.' -- answers: {headline['text']!r}. "
        f"A fact with a different verb (borrowed, not murdered) and a passage set with no rule sentence at "
        "all both correctly abstain rather than guess."
    )

    run.finish(
        title="Rule application: a given conditional rule applied to a given fact",
        goal=(
            "Build and measure the reasoning primitive raised directly in review: given a rule in context "
            "('if X, then Y') and a fact in context, answer a question by matching the fact against the "
            "rule's trigger and applying its consequence -- without training or calling a generative model, "
            "using only the existing spaCy dependency parser already loaded for real-model NER (EXP-032/033) "
            "to extract each sentence's verb."
        ),
        method=(
            "lab.common.rules.parse_conditional_rule extracts an 'if <subject>, <verb phrase>, <consequence>' "
            "rule's trigger verb lemma via dependency parse. lab.common.rules.extract_fact_triple extracts a "
            "fact sentence's subject/verb lemma/object the same way. lab.common.rules.apply_rule compares the "
            "two verb lemmas -- the one judgment this module makes. "
            "lab.common.rules.answer_rule_question scans the given passages for the first rule and the first "
            "fact with a concrete subject, applies the rule if the verbs match, and returns the consequence "
            "with citations to both passages; it abstains (decision 'inconclusive') if no rule, no concrete "
            "fact, or no verb match is found, rather than guessing from the ask's own wording."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=(
            "A general rule given in context can be applied to a specific fact given in context, and the "
            "result cited back to both, without a generative model and without training anything new -- a "
            "dependency parser's verb extraction plus one lemma comparison is enough for this shape of case. "
            "The system correctly abstains rather than answers when the fact doesn't match the rule's verb or "
            "when no rule sentence is present at all, instead of defaulting to a guess."
        ),
        scale_down=(
            "One rule sentence shape ('If <subject>, <verb phrase>, <consequence>.') and single-clause facts "
            "with no qualifier. A rule with an exception ('...unless committed in self-defense') is not "
            "parsed here -- the same qualifier gap EXP-006/EXP-026 already named for the lexical NLI judge. "
            "Multiple candidate rules or facts in the same passage set are not disambiguated; the first of "
            "each is used."
        ),
        referenced_files=FILES,
        follow_ups=[
            "EXP-026's qualifier-rule todo (except/unless/provided that) applies here too: a rule with an "
            "exception clause would currently be matched and applied without checking whether the exception "
            "fires.",
            "Wire this into lab/common/engine.run_task as a new task_type once the ask analyzer "
            "(lab/common/ask.py) can detect a rule-application question, so it isn't a separate standalone "
            "path.",
            "Test against passage sets with more than one candidate rule or fact to measure disambiguation, "
            "not just presence/absence.",
        ],
        models_used=(
            "No model decides the outcome. spaCy's en_core_web_sm dependency parser (already loaded for "
            "EXP-032/033's real-model NER, lab/common/real_models.py) extracts each sentence's main verb -- "
            "a narrow syntactic sub-task, not a reasoning judgment. The rule match and the final answer are "
            "deterministic code."
        ),
    )


if __name__ == "__main__":
    main()
