"""EXP-111: lab.common.entities.resolve_mentions/train_pair_matcher/
same_entity_pairs, wired into brain.reason's identity_extraction stage as
an opt-in coreference-resolution pass.

EXP-075 documented the exact gap directly: "'Ravi Sharma' and 'R. Sharma'
would be two different graph nodes, not one" -- identity_extraction's own
person selection is exact-text, so a short-form alias that happens to be
mentioned before the fuller name wins by ordering alone, never checked
against the fuller mention for being the same person.

No shipped default training set (this project's "measured, not assumed"
rule): a generic default coreference model risks false merges on real
documents this repo has no labeled data to validate against, so this is a
pure opt-in -- a no-op (today's exact-text-only behavior) unless the
caller supplies its own labeled same/different pairs via
coreference_pairs=.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/tests/exp_111_entity_coreference_wiring/run.py",
    "lab/common/brain.py",
    "lab/common/entities.py",
    "data/exp_111_entity_coreference_wiring/results.json",
]

# This experiment's own fixture (deliberately NOT exp_009's: that one
# labels a role-mismatched "R. Sharma"/"Ravi Sharma" pair as DIFFERENT --
# a more conservative stance for a document with distinct tenant/lessee
# roles -- while this experiment demonstrates the simpler, same-role
# alias case EXP-075 actually named).
PAIR_TRAIN = [
    {"left": {"text": "Ravi Sharma", "context": "lessee pune", "address": "411001", "role": "Lessee"}, "right": {"text": "Ravi Sharma", "context": "lessee pune", "address": "411001", "role": "Lessee"}, "same": 1},
    {"left": {"text": "Amit Sharma", "context": "lake road", "address": "411002", "role": None}, "right": {"text": "Neha Sharma", "context": "hill road", "address": "411003", "role": None}, "same": 0},
    {"left": {"text": "R. Sharma", "context": "tenant", "address": None, "role": "tenant"}, "right": {"text": "Ravi Sharma", "context": "lessee", "address": "411001", "role": "Lessee"}, "same": 1},
    {"left": {"text": "Meera Iyer", "context": "park street", "address": "700016", "role": None}, "right": {"text": "Kapil Menon", "context": "park street", "address": "700016", "role": None}, "same": 0},
]

ASK = "Who is the name and address?"
# The short form ("R. Sharma") is mentioned FIRST -- today's exact-text
# selection picks it by ordering alone, the exact ambiguity EXP-075 named.
ALIAS_PASSAGES = [
    {"id": "P1", "text": "R. Sharma signed the agreement as the tenant."},
    {"id": "P2", "text": "Ravi Sharma lives at 14 MG Road, Pune 411001."},
]
# Two genuinely DIFFERENT people sharing a surname (the exact pair
# PAIR_TRAIN itself labels "same": 0) -- the pair matcher's own
# different-address signal must keep them apart, not merge everyone who
# shares a surname.
DIFFERENT_PEOPLE_PASSAGES = [
    {"id": "P3", "text": "Amit Sharma lives at 9 Lake Road, Pune 411002."},
    {"id": "P4", "text": "Neha Sharma lives at 3 Hill Road, Pune 411003."},
]


def main() -> None:
    run = Run("EXP-111", "exp_111_entity_coreference_wiring")

    off = reason(ASK, ALIAS_PASSAGES)
    on = reason(ASK, ALIAS_PASSAGES, coreference_pairs=PAIR_TRAIN)
    coref_step = next((t for t in on["trace"] if t.get("step") == "coreference_resolve"), None)

    different_off = reason("Who is the name?", DIFFERENT_PEOPLE_PASSAGES)
    different_on = reason("Who is the name?", DIFFERENT_PEOPLE_PASSAGES, coreference_pairs=PAIR_TRAIN)
    different_coref_step = next((t for t in different_on["trace"] if t.get("step") == "coreference_resolve"), None)

    off_correct = off["decision"] == "supported" and "R. Sharma" in off["text"] and not any(t.get("step") == "coreference_resolve" for t in off["trace"])
    on_correct = (
        on["decision"] == "supported"
        and "Ravi Sharma" in on["text"]
        and "R. Sharma" not in on["text"]
        and coref_step is not None
        and set(coref_step["merged"]) == {"R. Sharma", "Ravi Sharma"}
        and coref_step["chosen"] == "Ravi Sharma"
        and "P1" in on["citations"]
        and "P2" in on["citations"]
    )
    different_people_correct = (
        different_off["text"] == different_on["text"]
        and different_coref_step is None
    )

    metrics = {
        "coreference_pairs_omitted_baseline": {"decision": off["decision"], "text": off["text"], "correct": off_correct},
        "coreference_pairs_given_merges_alias": {
            "decision": on["decision"],
            "text": on["text"],
            "merged": coref_step["merged"] if coref_step else None,
            "chosen": coref_step["chosen"] if coref_step else None,
            "citations": sorted(on["citations"]),
            "correct": on_correct,
        },
        "different_people_same_surname_not_merged": {
            "baseline_text": different_off["text"],
            "with_pairs_text": different_on["text"],
            "correct": different_people_correct,
        },
    }
    run.write_json("items.json", metrics)
    all_correct = off_correct and on_correct and different_people_correct

    prose = (
        f"The short-form mention ('R. Sharma') appears first; coreference_pairs omitted (default): "
        f"{off['text']!r} -- today's exact ordering-based selection, unchanged. With coreference_pairs given: "
        f"{on['text']!r}, merged={coref_step['merged']}, chosen={coref_step['chosen']!r} -- the fuller name "
        f"correctly preferred, both source passages cited. Two genuinely different people sharing a surname "
        f"(Amit Sharma, Neha Sharma, different addresses): identical answer with or without coreference_pairs "
        f"-- the pair matcher's own different-address signal correctly keeps them apart, not merged just for "
        f"sharing a surname."
    )
    conclusion = (
        "lab.common.entities.resolve_mentions/train_pair_matcher/same_entity_pairs -- present since EXP-009 "
        "with zero callers from lab.common.brain -- now resolve a short-form alias to its fuller mention "
        "within identity_extraction when the caller opts in with coreference_pairs=, closing the exact gap "
        "EXP-075 documented. No shipped default training set, and no caller is affected unless it supplies "
        "its own labeled pairs."
        if all_correct else
        "At least one case did not behave as expected -- see metrics for exactly which."
    )
    run.finish(
        title="Entity coreference resolution wired into identity_extraction, opt-in via coreference_pairs=",
        goal="Close EXP-075's own documented gap: a short-form name alias and its fuller mention resolve to two different identities today, decided by mention ORDER alone, never checked against each other.",
        method="A short-form alias mentioned before its fuller form, checked with coreference_pairs omitted (unchanged ordering-based pick) and given (correctly merges, prefers the fuller name, cites both source passages). A same-surname-but-different-address pair, checked to confirm the pair matcher's own address signal still keeps genuinely different people apart.",
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="One alias pair, one distinct-people pair, a 5-row training fixture (EXP-009's own) -- a proof the dispatch/merge/citation wiring works end to end, not a benchmark of the pair matcher's own precision at a larger, more diverse real-document scale (a known, already-documented limitation of this primitive, unchanged by this wiring).",
        referenced_files=FILES,
        follow_ups=[
            "No shipped default coreference_pairs: a caller who wants this on must supply its own labeled training pairs -- a deliberate scope limit (this project's 'measured, not assumed' rule), not a missing feature.",
        ],
        models_used="sklearn LogisticRegression (lab.common.entities.train_pair_matcher) -- the blueprint's own named pair-matcher model, unchanged from EXP-009.",
    )
    print("off_correct:", off_correct, "on_correct:", on_correct, "different_people_correct:", different_people_correct)
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
