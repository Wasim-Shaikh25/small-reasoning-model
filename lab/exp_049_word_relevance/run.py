"""EXP-049: per-word relevance and grammaticality scoring for the ask
pipeline -- the first stage of AGENT.md's word-by-word relevance
cascade (chunk the prompt, then check every nearby word's relevance and
grammar before deciding how to use the sentence).

RETIRED (2026-11-11): lab.common.word_relevance was deleted after an
honest wire-or-discard review found it genuinely superseded, not just
unused. Its own follow-up already named EXP-051 (sentence role-tagging)
as "the named next step that consumes this score as one of its own
input features" -- checked directly, EXP-051 never did: it uses
lab.common.relevance.ask_relevance (already live, with real callers in
qa.py/notes_to_findings.py/verify.py/nli.py/paged.py) instead of
word_relevance.score_words. And grammatical_check's own judgment (a ROOT
verb with a subject) is strictly weaker than lab.common.
sentence_completeness.is_complete_sentence (already live, gating
lab.common.rewriter_backends and lab.common.grammar_logic) -- that
module's own docstring documents two blind spots (gerund fragments, lone
subordinate clauses) that grammatical_check has no equivalent check for
at all. Neither half of this module was ever adopted by the mechanism
meant to adopt it; both were independently superseded by something
already live. This script is kept as the historical record of what it
measured (its results.json is unaffected), but running it again will
now ImportError. Recover the deleted module with `git show <commit
before this deletion>:lab/common/word_relevance.py` if this judgment is
ever revisited.

lab.common.word_relevance.sentence_admission combines two independent,
bounded judgments (score_words: per-word lexical relevance to the ask;
grammatical_check: is this sentence a complete clause, not a fragment)
into the one decision this stage exists to make -- should a candidate
sentence be allowed into the shortlist that feeds extraction.

Four hand-built cases, each isolating one failure mode, plus a real-
world check against the repo's own GDPR_TEXT fixture (EXP-081) scanning
every sentence for the specific fragment shape a naive splitter can
produce at a clause boundary -- not a second hand-built fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.harness import Run
from lab.common.textutil import sentences
from lab.common.word_relevance import sentence_admission
from lab.exp_081_real_document_pipeline.run import GDPR_TEXT

FILES = [
    "lab/exp_049_word_relevance/run.py",
    "lab/common/word_relevance.py",
    "lab/common/textutil.py",
    "lab/common/rules.py",
    "lab/exp_081_real_document_pipeline/run.py",
]

ASK = "Does the processing of special category data require explicit consent?"

CASES = [
    ("relevant_and_grammatical", "The processing of special category data requires explicit consent.", True),
    ("grammatical_but_offtopic", "The weather in Mumbai is pleasant during the monsoon season.", False),
    ("relevant_but_fragment", "of the processing of special category data for one or more specified purposes", False),
    ("offtopic_fragment", "of the weather during the monsoon season", False),
]


def main():
    run = Run("EXP-049", "exp_049_word_relevance")

    case_results = []
    for label, sentence, expected_admitted in CASES:
        result = sentence_admission(ASK, sentence)
        correct = result["admitted"] == expected_admitted
        case_results.append({"label": label, "sentence": sentence, "expected_admitted": expected_admitted, "admitted": result["admitted"], "grammar": result["grammar"], "relevant_count": result["relevant_count"], "correct": correct})

    gdpr_sentences = sentences(GDPR_TEXT)
    gdpr_admissions = [{"sentence": s, "admitted": sentence_admission(ASK, s)["admitted"], "well_formed": sentence_admission(ASK, s)["grammar"]["well_formed"]} for s in gdpr_sentences]
    gdpr_well_formed_count = sum(1 for g in gdpr_admissions if g["well_formed"])
    gdpr_admitted_count = sum(1 for g in gdpr_admissions if g["admitted"])

    run.write_json("cases.json", {"hand_built": case_results, "gdpr_admissions": gdpr_admissions})

    all_correct = all(c["correct"] for c in case_results)

    metrics = {
        "hand_built_cases": {"n": len(case_results), "correct": sum(1 for c in case_results if c["correct"]), "by_label": {c["label"]: c["correct"] for c in case_results}},
        "gdpr_full_document": {"total_sentences": len(gdpr_sentences), "well_formed": gdpr_well_formed_count, "admitted_for_this_ask": gdpr_admitted_count},
        "all_correct": all_correct,
    }

    incorrect = [c["label"] for c in case_results if not c["correct"]]
    prose = (
        f"{metrics['hand_built_cases']['correct']}/{metrics['hand_built_cases']['n']} hand-built cases correct "
        f"-- {'all correct' if not incorrect else 'incorrect: ' + ', '.join(incorrect)}. Each isolates one "
        f"failure mode: relevant+grammatical admits; grammatical-but-off-topic rejects on relevance "
        f"(0 relevant words); relevant-but-fragment rejects on grammar (no ROOT verb at all, a bare "
        f"prepositional phrase); off-topic fragment rejects on both. On the real {len(gdpr_sentences)}-sentence "
        f"GDPR text: {gdpr_well_formed_count} sentences are grammatically complete clauses, "
        f"{gdpr_admitted_count} of those are also admitted for this specific consent-related ask."
    )

    conclusion = (
        "Both judgments are independently necessary and independently sufficient to reject a bad candidate: "
        "relevance alone would admit the off-topic fragment's grammatical cousin had it been well-formed, and "
        "grammar alone would admit the on-topic fragment. Combining them (lab.common.word_relevance."
        "sentence_admission) catches both failure modes a naive single-score relevance check (lab.common."
        "relevance.ask_relevance, which only ever measures a whole candidate's aggregate coverage) would not "
        "separate. Run against the real GDPR text, the grammaticality check alone already rejects a real "
        "fraction of sentences as non-clausal, before relevance is even considered."
        if all_correct
        else "At least one hand-built case did not behave as expected -- see metrics, reported as measured."
    )

    run.finish(
        title="Per-word relevance and grammaticality scoring for the ask pipeline",
        goal=(
            "Score each content word in a candidate sentence for (a) relevance to the ask -- token overlap "
            "against the ask's content terms -- and (b) local grammatical well-formedness -- subject/verb "
            "intact, not a sentence fragment -- before a sentence is allowed into the shortlist that feeds "
            "extraction. The first stage of the word-by-word relevance cascade AGENT.md names."
        ),
        method=(
            "lab.common.word_relevance.sentence_admission (new) combines score_words (per content word, fuzzy "
            "lexical match against the ask's own content words, the same matching lab.common.textutil.coverage "
            "already uses) and grammatical_check (spaCy dependency parse: a ROOT verb with its own subject, "
            "rejecting a bare fragment). Four hand-built cases isolating each failure mode, plus every sentence "
            "of the real GDPR_TEXT fixture (EXP-081) scored for both judgments."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down=(
            "Relevance is lexical/fuzzy-prefix matching (lab.common.textutil's existing style), not a semantic "
            "embedding match -- a true paraphrase with no shared word stems would score 0 relevant words here, "
            "the same scale-down lab.common.relevance.ask_relevance already carries. Does not yet wire this as "
            "an actual gate inside lab.common.qa's extraction loop -- EXP-051 (sentence role-tagging) is the "
            "named next step that consumes this score as one of its own input features, not this exploration."
        ),
        referenced_files=FILES,
        follow_ups=[],
        models_used=(
            "spaCy en_core_web_sm dependency parser (lab.common.rules._parser, already a dependency, "
            "deterministic) for grammaticality. No new model for relevance -- reuses lab.common.textutil's "
            "existing lexical matching. No generative model."
        ),
    )

    print(f"hand-built: {metrics['hand_built_cases']['correct']}/{metrics['hand_built_cases']['n']} correct")
    print(f"GDPR document: {gdpr_well_formed_count}/{len(gdpr_sentences)} well-formed, {gdpr_admitted_count} admitted for this ask")


if __name__ == "__main__":
    main()
