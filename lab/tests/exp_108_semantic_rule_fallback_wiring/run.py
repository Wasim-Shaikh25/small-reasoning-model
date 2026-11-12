"""EXP-108: lab.common.rules.semantic_apply_rule, wired into brain.reason's
rule_application stage as a paraphrase-robust fallback for apply_rule's
exact-lemma match.

EXP-061 already measured semantic_apply_rule (real NLI entailment) against
apply_rule (exact lemma) as a standalone comparison -- this wires it
directly into the live rule_application stage itself, not just a
side-by-side script. apply_rule's own fact_passage search is exact-lemma
ONLY: when a fact never shares the rule's trigger verb lemma
("unlawfully took her life" vs "murders"), fact_passage comes back None
and the rule silently falls through to lookup_fallback, no matter how
clearly the fact means the same thing.

Gated on use_real_nli (already an existing reason() flag, not a new one):
only ever attempted when the caller already opted into a real NLI
checkpoint, and only as a fallback AFTER the exact-lemma search already
failed -- never consulted, and never able to change a result, for any
caller that leaves use_real_nli at its default False, or whose fact DOES
share the rule's trigger lemma.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run

FILES = [
    "lab/tests/exp_108_semantic_rule_fallback_wiring/run.py",
    "lab/common/brain.py",
    "lab/common/rules.py",
    "lab/common/real_encoders.py",
    "data/exp_108_semantic_rule_fallback_wiring/results.json",
]

RULE_PASSAGE = {"id": "R1", "text": "If someone murders a person, it is a punishable crime."}
PARAPHRASED_FACT = {"id": "F1", "text": "Arjun unlawfully took the life of Neha."}
EXACT_FACT = {"id": "F2", "text": "Arjun murdered Neha."}
UNRELATED_FACT = {"id": "F3", "text": "Priya resigned from her job."}
ASK = "Did Arjun violate a rule?"


def main() -> None:
    run = Run("EXP-108", "exp_108_semantic_rule_fallback_wiring")

    no_flag = reason(ASK, [RULE_PASSAGE, PARAPHRASED_FACT])
    with_flag = reason(ASK, [RULE_PASSAGE, PARAPHRASED_FACT], use_real_nli=True)
    semantic_step = next((t for t in with_flag["trace"] if t.get("step") == "apply_rule" and t.get("kind") == "verb_semantic"), None)

    exact_still_works = reason(ASK, [RULE_PASSAGE, EXACT_FACT], use_real_nli=True)
    exact_step = next((t for t in exact_still_works["trace"] if t.get("step") == "apply_rule" and t.get("kind") == "verb"), None)

    no_match_at_all = reason(ASK, [RULE_PASSAGE, UNRELATED_FACT], use_real_nli=True)

    no_flag_correct = no_flag["decision"] == "inconclusive"
    with_flag_correct = (
        with_flag["decision"] == "supported"
        and semantic_step is not None
        and semantic_step["result"]["matched"]
        and "F1" in with_flag["citations"]
        and "R1" in with_flag["citations"]
    )
    exact_correct = (
        exact_still_works["decision"] == "supported"
        and exact_step is not None
        and exact_step["kind"] == "verb"
    )
    no_match_correct = no_match_at_all["decision"] == "inconclusive"

    metrics = {
        "use_real_nli_omitted_baseline": {"decision": no_flag["decision"], "correct": no_flag_correct},
        "paraphrased_fact_with_flag": {
            "decision": with_flag["decision"],
            "citations": sorted(with_flag["citations"]),
            "semantic_match_nli": semantic_step["result"]["nli"] if semantic_step else None,
            "correct": with_flag_correct,
        },
        "exact_match_unaffected_by_flag": {"decision": exact_still_works["decision"], "method": exact_step["kind"] if exact_step else None, "correct": exact_correct},
        "truly_unrelated_fact_still_abstains": {"decision": no_match_at_all["decision"], "correct": no_match_correct},
    }
    run.write_json("items.json", metrics)
    all_correct = no_flag_correct and with_flag_correct and exact_correct and no_match_correct

    prose = (
        f"A fact phrased without the rule's trigger verb lemma, use_real_nli omitted (today's default): "
        f"{no_flag['decision']!r} -- apply_rule's exact-lemma search finds no fact_passage, same as before "
        f"this wiring existed. The SAME case with use_real_nli=True: {with_flag['decision']!r}, matched via "
        f"the new 'verb_semantic' trace kind, citations={sorted(with_flag['citations'])}. An EXACT-lemma "
        f"fact with use_real_nli=True still resolves through the ordinary exact-match path ('verb' kind), "
        f"never the semantic fallback -- the fallback only ever runs after the exact search already failed. "
        f"A genuinely unrelated fact still correctly abstains even with the flag set."
    )
    conclusion = (
        "lab.common.rules.semantic_apply_rule -- measured standalone in EXP-061, never wired into the live "
        "rule_application stage -- now runs as an explicit fallback when apply_rule's exact-lemma search "
        "finds no fact_passage at all, gated on the EXISTING use_real_nli flag (no new parameter). Zero "
        "regression: every caller who leaves use_real_nli at its default, or whose fact already shares the "
        "rule's trigger lemma, takes the exact same path as before this wiring existed."
        if all_correct else
        "At least one case did not behave as expected -- see metrics for exactly which."
    )
    run.finish(
        title="semantic_apply_rule wired into rule_application as a use_real_nli-gated fallback for apply_rule's exact-lemma miss",
        goal="Close the gap EXP-061 measured standalone but never wired: a fact phrased without the rule's own trigger verb lemma falls through to lookup_fallback today, even when it clearly satisfies the rule's condition by meaning.",
        method="A paraphrased fact (no shared lemma) checked with the flag omitted (today's exact behavior, abstains) and set (resolves via the new fallback). An exact-lemma fact checked with the flag set, to confirm it still takes the ordinary path, never the fallback. A genuinely unrelated fact checked with the flag set, to confirm abstention still works when nothing actually matches.",
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="One rule, one paraphrased fact, one exact fact, one unrelated fact -- a proof the dispatch/gating/citation wiring works end to end, not a benchmark of the real NLI checkpoint's own paraphrase-matching precision at scale (already measured separately in EXP-061/EXP-031).",
        referenced_files=FILES,
        follow_ups=[
            "The fallback does not run forward_chain (multi-rule chaining) the way the exact-match path does for a derived fact -- a semantically-matched fact that itself triggers a second rule stops after the first consequence, a deliberate scope limit, not an oversight.",
        ],
        models_used="lab.common.real_encoders.real_nli (DeBERTa-v3-base-mnli-fever-anli), only when the caller already set use_real_nli=True -- the classical lab.common.nli.judge remains the default judge_fn for any other (test/direct) caller of semantic_apply_rule.",
    )
    print("no_flag_correct:", no_flag_correct, "with_flag_correct:", with_flag_correct, "exact_correct:", exact_correct, "no_match_correct:", no_match_correct)
    print("ALL CORRECT:", all_correct)


if __name__ == "__main__":
    main()
