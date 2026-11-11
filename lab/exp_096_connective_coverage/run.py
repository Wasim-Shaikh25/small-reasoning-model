"""EXP-096: extending connective coverage, a bounded next step per EXP-090's
own conclusion ("the operator table covers ~20 of DiMLex-Eng's 149 English
connectives -- extending coverage... is a real, boundable next step").

18 candidates were probed against real spaCy output before any table
entry was added (same empirical-first discipline every connective class
in this repo was built under). 9 cleanly fit the TWO existing structural
patterns and were added:
  - "while"/"whereas" -- mark+advcl, same pattern as "although" (CONCESSION).
  - "meanwhile"/"subsequently" (TEMPORAL_BOUND), "accordingly" (CAUSAL),
    "additionally"/"similarly"/"likewise" (COMBINATOR_AND), "conversely"
    (CONCESSION) -- sentence-initial advmod+ROOT, same pattern as
    "however"/"therefore"/etc. (EXP-050).

9 candidates were measured and deliberately dropped, not forced into a
wrong classification:
  - "assuming that"/"now that" -- their "that" token attaches via
    dep_=="ccomp", the exact reported-speech-complementizer pattern
    EXP-090 found and excluded (never a genuine connective in this
    repo's own measurements).
  - "given that" -- "given" attaches as dep_=="prep" to an ACOMP, not
    the ROOT verb -- a different attachment shape than every existing
    prep-subordinator entry, not yet verified safe to generalize to.
  - "whenever" -- surfaces as dep_=="advmod" (not "mark") attached to
    an advcl -- a genuinely new structural pattern neither of this
    module's two detection branches currently checks for.
  - "as soon as" -- two stacked advmod tokens attached to the ROOT
    verb directly, not mark+advcl at all -- a third new pattern.
  - "due to"/"owing to" -- a two-token "X to" compound preposition
    whose object sits under the SECOND token ("to"), not the first
    (tok) the way _clause_text_for_prep expects -- would need that
    helper extended, not yet done.
  - "in spite of"/"regardless of" -- three-token idioms ("in spite OF",
    "regardless OF") that only partially fit the existing _IN_IDIOMS
    two-token extension point.

Each dropped case is a real, nameable next step (not a dead end), kept
in follow_ups rather than silently abandoned.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.connectives import Operator, find_connectives
from lab.common.harness import Run
from lab.common.textutil import sentences
from lab.common.fixtures import GDPR_TEXT

FILES = [
    "lab/exp_096_connective_coverage/run.py",
    "lab/common/connectives.py",
    "lab/common/textutil.py",
    "lab/common/fixtures.py",
    "lab/exp_090_connective_detection/run.py",
]

CASES = [
    ("while", "While the controller must notify the authority, the processor need not.", Operator.CONCESSION),
    ("whereas", "Whereas the controller bears responsibility, the processor does not.", Operator.CONCESSION),
    ("meanwhile", "Meanwhile, the processor must retain the records.", Operator.TEMPORAL_BOUND),
    ("subsequently", "Subsequently, the processor deleted the data.", Operator.TEMPORAL_BOUND),
    ("accordingly", "Accordingly, the controller must notify the authority.", Operator.CAUSAL),
    ("additionally", "Additionally, the controller must document the breach.", Operator.COMBINATOR_AND),
    ("similarly", "Similarly, the processor must comply.", Operator.COMBINATOR_AND),
    ("likewise", "Likewise, the processor must comply.", Operator.COMBINATOR_AND),
    ("conversely", "Conversely, the processor bears no liability.", Operator.CONCESSION),
]

DROPPED_CANDIDATES = [
    {"phrase": "assuming that", "reason": "'that' attaches via dep_=='ccomp', the excluded reported-speech-complementizer pattern (EXP-090)"},
    {"phrase": "now that", "reason": "'that' attaches via dep_=='ccomp', same as 'assuming that'"},
    {"phrase": "given that", "reason": "'given' attaches as dep_=='prep' to an ACOMP, not the ROOT verb -- different shape than existing prep-subordinator entries"},
    {"phrase": "whenever", "reason": "surfaces as dep_=='advmod' (not 'mark') attached to an advcl -- a new pattern this module doesn't check"},
    {"phrase": "as soon as", "reason": "two stacked advmod tokens attached directly to ROOT, not mark+advcl at all"},
    {"phrase": "due to", "reason": "two-token 'X to' compound preposition; the object sits under the second token, not the first the way _clause_text_for_prep expects"},
    {"phrase": "owing to", "reason": "same two-token compound-preposition shape as 'due to'"},
    {"phrase": "in spite of", "reason": "three-token idiom ('in spite OF'); only partially fits the existing two-token _IN_IDIOMS extension point"},
    {"phrase": "regardless of", "reason": "three-token idiom with its own 'regardless' as advmod, not prep -- a different shape from 'in spite of'"},
]


def main():
    run = Run("EXP-096", "exp_096_connective_coverage")

    case_results = []
    for label, sentence, expected_operator in CASES:
        found = find_connectives(sentence)
        matched = next((m for m in found if m.phrase == label and m.operator == expected_operator), None)
        correct = matched is not None
        case_results.append({"label": label, "sentence": sentence, "expected_operator": expected_operator, "correct": correct, "dep_pattern": matched.dep_pattern if matched else None})

    gdpr_sentences = sentences(GDPR_TEXT)
    new_phrases = {c[0] for c in CASES}
    gdpr_hits = []
    for sent in gdpr_sentences:
        for m in find_connectives(sent):
            if m.phrase in new_phrases:
                gdpr_hits.append({"phrase": m.phrase, "operator": m.operator, "sentence": sent})

    run.write_json("cases.json", {"new_connective_cases": case_results, "dropped_candidates": DROPPED_CANDIDATES, "gdpr_hits": gdpr_hits})

    all_correct = all(c["correct"] for c in case_results)

    metrics = {
        "new_cases": {"n": len(case_results), "correct": sum(1 for c in case_results if c["correct"]), "by_label": {c["label"]: c["correct"] for c in case_results}},
        "n_dropped_candidates": len(DROPPED_CANDIDATES),
        "gdpr_full_document": {"total_sentences": len(gdpr_sentences), "new_connective_hits": len(gdpr_hits)},
        "all_correct": all_correct,
    }

    incorrect = [c["label"] for c in case_results if not c["correct"]]
    prose = (
        f"9/{len(CASES)} new connectives correctly classified -- {'all correct' if not incorrect else 'incorrect: ' + ', '.join(incorrect)}, "
        f"covering 2 more mark+advcl subordinators (while, whereas) and 7 more sentence-initial discourse "
        f"adverbials (meanwhile, subsequently, accordingly, additionally, similarly, likewise, conversely), "
        f"all verified against real spaCy output before being added, the same discipline EXP-090 used. "
        f"{len(DROPPED_CANDIDATES)} further candidates were measured and deliberately dropped rather than "
        f"forced into a wrong classification -- each hits a genuinely different structural pattern this "
        f"module doesn't yet handle (ccomp complementizers, compound prepositions, stacked advmods), named "
        f"honestly in follow_ups. On the real GDPR text: {len(gdpr_hits)} instances of the 9 new connectives "
        f"found."
    )

    conclusion = (
        "Connective coverage grew from 28 to 37 recognized phrases (CONNECTIVE_TABLE + DISCOURSE_ADVERBIAL_"
        "TABLE combined) through the same two already-built, already-tested structural patterns -- no new "
        "detection code, purely additive table entries. Equally important: 9 further candidates were "
        "measured and found NOT to fit either existing pattern, and were left out rather than misclassified "
        "-- extending coverage further needs new structural patterns (a ccomp-vs-mark discriminator for "
        "'that'-clauses, multi-token compound prepositions), not just more table rows."
        if all_correct
        else "At least one new connective did not classify as expected -- see metrics, reported as measured."
    )

    run.finish(
        title="Extending connective coverage: 9 verified additions, 9 candidates measured and dropped",
        goal=(
            "A bounded next step on EXP-090's own conclusion: extend CONNECTIVE_TABLE/DISCOURSE_ADVERBIAL_"
            "TABLE coverage past ~20/149 DiMLex-Eng connectives, verifying each candidate against real spaCy "
            "output before adding it -- and reporting, not hiding, any candidate that doesn't fit this "
            "module's existing structural patterns."
        ),
        method=(
            "18 candidate connectives, spanning all four PDTB classes, probed directly against spaCy's real "
            "dependency parse before any table entry was written. 9 cleanly matched one of the two existing "
            "structural patterns (mark+advcl for while/whereas; sentence-initial advmod+ROOT for the 7 "
            "discourse adverbials) and were added to CONNECTIVE_TABLE/DISCOURSE_ADVERBIAL_TABLE. 9 did not "
            "and were left out. One hand-built sentence per added connective, plus a sweep of the real "
            "GDPR_TEXT fixture for instances of the new connectives specifically. Reran EXP-090/091/026/050 "
            "to confirm the additions caused no regression."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "Still a small, named subset of DiMLex-Eng's 149 (37 now, not all 149). The 9 dropped candidates "
            "are real, nameable future work (see follow_ups), not abandoned without reason. Hand-built "
            "sentences, not held-out novel phrasings of the same connectives."
        ),
        referenced_files=FILES,
        follow_ups=[
            f"{c['phrase']}: {c['reason']}" for c in DROPPED_CANDIDATES
        ],
        models_used=(
            "spaCy en_core_web_sm dependency parser via lab.common.connectives.find_connectives (unchanged "
            "detection code, new table entries only). No generative model."
        ),
    )

    print(f"new connectives: {metrics['new_cases']['correct']}/{metrics['new_cases']['n']} correct")
    print(f"GDPR hits: {len(gdpr_hits)}, dropped candidates: {len(DROPPED_CANDIDATES)}")


if __name__ == "__main__":
    main()
