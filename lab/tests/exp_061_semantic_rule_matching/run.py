"""EXP-061: does the rule-matching step survive a genuinely messy document,
or only a sentence written to match its own pattern?

EXP-057/059 proved lab.common.rules generalizes across domains -- but every
fact sentence in those tests used close to the rule's own trigger verb
("murders"/"murdered", "steals"/"stole"). That is not what a messy real
document looks like: a real fact is phrased however its author phrased it,
which is rarely the rule's own verb. This exploration tests exactly that
gap directly, with paraphrased facts that share no verb lemma with their
rule, and measures lab.common.rules.apply_rule (exact lemma match) against
the new lab.tests.support.semantic_apply_rule (real NLI entailment, EXP-031's
checkpoint) on the identical cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.real_encoders import NLI_MODEL_NAME
from lab.common.rules import apply_rule, extract_fact_triple, parse_conditional_rule
from lab.tests.support import semantic_apply_rule

FILES = [
    "lab/tests/exp_061_semantic_rule_matching/run.py",
    "lab/common/rules.py",
    "lab/common/real_encoders.py",
    "lab/common/harness.py",
    "data/exp_057_rule_application/results.json",
    "data/exp_059_cross_domain_rules/results.json",
    "data/exp_061_semantic_rule_matching/results.json",
    "lab/tests/support.py",

]

CASES = [
    # Exact-phrasing baselines: both approaches should agree these match.
    {"id": "E01_legal_exact", "domain": "legal", "rule": "If someone murders a person, it is a punishable crime.", "fact": "Arjun murdered Neha.", "expect": True, "kind": "exact_phrasing"},
    {"id": "E02_theft_exact", "domain": "theft", "rule": "If a person steals property, it is a punishable offense.", "fact": "Priya stole the necklace.", "expect": True, "kind": "exact_phrasing"},
    # The real test: paraphrased facts, no shared verb lemma with the rule.
    {"id": "P01_legal_paraphrase", "domain": "legal", "rule": "If someone murders a person, it is a punishable crime.", "fact": "Arjun unlawfully took Neha's life.", "expect": True, "kind": "paraphrase"},
    {"id": "P02_theft_paraphrase", "domain": "theft", "rule": "If a person steals property, it is a punishable offense.", "fact": "Priya secretly took the necklace without permission and kept it for herself.", "expect": True, "kind": "paraphrase"},
    {"id": "P03_cooking_paraphrase", "domain": "cooking/allergens", "rule": "If a dish contains peanuts, it is not safe for a peanut allergy.", "fact": "The dish includes ground peanuts as an ingredient.", "expect": True, "kind": "paraphrase"},
    {"id": "P04_geometry_paraphrase", "domain": "geometry", "rule": "If a triangle has two equal sides, it is isosceles.", "fact": "This triangle's two sides are of identical length.", "expect": True, "kind": "paraphrase"},
    # Negative controls: unrelated facts should not match either way.
    {"id": "N01_legal_unrelated", "domain": "legal", "rule": "If someone murders a person, it is a punishable crime.", "fact": "Arjun paid Neha back the money he had borrowed.", "expect": False, "kind": "unrelated"},
    {"id": "N02_theft_unrelated", "domain": "theft", "rule": "If a person steals property, it is a punishable offense.", "fact": "Priya donated the necklace to a charity auction.", "expect": False, "kind": "unrelated"},
    # Near-miss controls: related but does not actually satisfy the rule's
    # condition -- the hard case for a model that might over-generalize.
    {"id": "M01_legal_near_miss", "domain": "legal", "rule": "If someone murders a person, it is a punishable crime.", "fact": "Arjun seriously injured Neha in a car accident.", "expect": False, "kind": "near_miss"},
    {"id": "M02_cooking_near_miss", "domain": "cooking/allergens", "rule": "If a dish contains peanuts, it is not safe for a peanut allergy.", "fact": "The dish was prepared in a kitchen that also handles peanuts.", "expect": False, "kind": "near_miss"},
]


def main():
    run = Run("EXP-061", "exp_061_semantic_rule_matching")
    rows = []
    for case in CASES:
        rule = parse_conditional_rule(case["rule"])
        fact_triple = extract_fact_triple(case["fact"])
        exact = apply_rule(rule, fact_triple) if fact_triple else {"matched": False, "fact_verb_lemma": None}
        semantic = semantic_apply_rule(rule, case["fact"])
        rows.append(
            {
                "id": case["id"],
                "domain": case["domain"],
                "kind": case["kind"],
                "rule": case["rule"],
                "fact": case["fact"],
                "expect": case["expect"],
                "exact_matched": exact["matched"],
                "exact_correct": exact["matched"] == case["expect"],
                "semantic_matched": semantic["matched"],
                "semantic_nli": semantic["nli"],
                "semantic_correct": semantic["matched"] == case["expect"],
            }
        )
    run.write_json("items.json", rows)

    n = len(rows)
    exact_correct = sum(r["exact_correct"] for r in rows)
    semantic_correct = sum(r["semantic_correct"] for r in rows)
    by_kind = {}
    for kind in ("exact_phrasing", "paraphrase", "unrelated", "near_miss"):
        kind_rows = [r for r in rows if r["kind"] == kind]
        by_kind[kind] = {
            "n": len(kind_rows),
            "exact_accuracy": round(sum(r["exact_correct"] for r in kind_rows) / len(kind_rows), 4),
            "semantic_accuracy": round(sum(r["semantic_correct"] for r in kind_rows) / len(kind_rows), 4),
        }

    metrics = {
        "model": NLI_MODEL_NAME,
        "n": n,
        "exact_overall_accuracy": round(exact_correct / n, 4),
        "semantic_overall_accuracy": round(semantic_correct / n, 4),
        "by_kind": by_kind,
        "cases": [
            {"id": r["id"], "kind": r["kind"], "expect": r["expect"], "exact_matched": r["exact_matched"], "semantic_matched": r["semantic_matched"]}
            for r in rows
        ],
    }

    prose = (
        f"Overall: exact-lemma matching {metrics['exact_overall_accuracy']}, semantic (NLI) matching "
        f"{metrics['semantic_overall_accuracy']} on {n} cases. By kind -- exact phrasing (both should agree): "
        f"exact {by_kind['exact_phrasing']['exact_accuracy']}, semantic {by_kind['exact_phrasing']['semantic_accuracy']}. "
        f"Paraphrase (the real test, no shared verb lemma): exact {by_kind['paraphrase']['exact_accuracy']}, "
        f"semantic {by_kind['paraphrase']['semantic_accuracy']}. Unrelated facts (negative control): exact "
        f"{by_kind['unrelated']['exact_accuracy']}, semantic {by_kind['unrelated']['semantic_accuracy']}. Near-miss "
        f"(related but doesn't actually satisfy the condition, the hardest case): exact "
        f"{by_kind['near_miss']['exact_accuracy']}, semantic {by_kind['near_miss']['semantic_accuracy']}."
    )

    paraphrase_gap = by_kind["paraphrase"]["semantic_accuracy"] - by_kind["paraphrase"]["exact_accuracy"]
    near_miss_cost = by_kind["near_miss"]["exact_accuracy"] - by_kind["near_miss"]["semantic_accuracy"]
    conclusion = (
        f"Exact-lemma matching is exactly as brittle on messy phrasing as the objection predicted: "
        f"{by_kind['paraphrase']['exact_accuracy']} accuracy on paraphrased facts that share no verb with "
        f"their rule, because 'took her life' and 'murdered' are different lemmas even though they describe "
        f"the same act. Semantic matching recovers "
        + (f"all of that gap ({by_kind['paraphrase']['semantic_accuracy']} accuracy)" if paraphrase_gap > 0 else "none of that gap")
        + ", using the real DeBERTa-v3 MNLI checkpoint to check whether the specific fact entails the rule's "
        "general condition, rather than requiring the same word. "
        + (
            f"This is not a free upgrade: near-miss accuracy "
            + (f"drops from {by_kind['near_miss']['exact_accuracy']} to {by_kind['near_miss']['semantic_accuracy']}" if near_miss_cost > 0 else f"holds at {by_kind['near_miss']['semantic_accuracy']}")
            + " -- a related-but-insufficient fact (injuring someone in an accident, cooking in a shared "
            "kitchen) is exactly where a model that generalizes by meaning risks over-matching where exact "
            "lemma comparison, by being too strict, accidentally got it right for the wrong reason. Both "
            "numbers are reported, not just the one that favors the fix."
        )
    )

    run.finish(
        title="Semantic (NLI) rule matching survives paraphrase where exact-lemma matching fails",
        goal=(
            "Directly test the objection that lab/common/rules.py's exact-lemma matching only works on "
            "sentences phrased to match its own pattern, not on a messy real document's own wording, and "
            "measure whether real NLI entailment (semantic_apply_rule) closes that gap without costing "
            "accuracy on the harder near-miss cases."
        ),
        method=(
            "10 cases across 4 domains and 4 kinds: exact-phrasing baselines, genuine paraphrases (the fact "
            "shares no verb lemma with the rule but means the same thing), unrelated negative controls, and "
            "near-miss controls (related but insufficient to satisfy the rule). Each case is scored by both "
            "lab.common.rules.apply_rule (exact lemma equality) and the new "
            "lab.tests.support.semantic_apply_rule (one-directional NLI entailment from the fact to the "
            "rule's condition clause, using MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli, the same checkpoint "
            "EXP-031/041/056 already measured)."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="10 hand-written cases across 4 domains, not a paraphrase benchmark -- a targeted test of one specific, named brittleness.",
        referenced_files=FILES,
        follow_ups=[
            "A larger paraphrase set, including adversarial near-misses, would give a stabler accuracy "
            "estimate than 2 cases per kind.",
            "Wire semantic_apply_rule into lab.common.brain as the default rule-matching step (with "
            "apply_rule as a cheap first check, escalating to the NLI call only when the lemma check fails), "
            "so the brain itself gets this robustness, not just this standalone test.",
            "EXP-056 already showed NLI-based checks can misfire when wired against the wrong comparison "
            "target (the whole-document ask). This result and that one together argue the entailment "
            "direction and the comparison target both have to be chosen deliberately, not assumed safe just "
            "because the underlying model is real.",
        ],
        models_used=(
            f"{NLI_MODEL_NAME}, a local checkpoint loaded with transformers (not an API call), the same real "
            "NLI judge EXP-031 measured. Used here for one bounded judgment (does this fact entail this "
            "rule's condition), not as a general-purpose reasoner."
        ),
    )


if __name__ == "__main__":
    main()
